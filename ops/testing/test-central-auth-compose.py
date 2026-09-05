#!/usr/bin/env python3
"""Exercise the production auth Compose wiring using disposable volumes and networks.

Build central/auth/Dockerfile first, then pass the local image tag as the argument.
No existing containers, volumes, or host ports are used.
"""

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid


ROOT = Path(__file__).resolve().parents[2]
IMAGE = sys.argv[1] if len(sys.argv) == 2 else None
if not IMAGE:
    raise SystemExit("Usage: test-central-auth-compose.py LOCAL_AUTH_IMAGE")


def run(*args, stdin=None, check=True):
    result = subprocess.run(args, input=stdin, text=True, capture_output=True)
    if check and result.returncode:
        raise RuntimeError(f"Command failed: {args[0:3]}\n{result.stdout}\n{result.stderr}")
    return result.stdout.strip()


production = json.loads(run(
    "docker", "compose", "-f", str(ROOT / "ops/unicron/docker-compose.unicron.yaml"),
    "--env-file", str(ROOT / "ops/unicron/.env.example"), "config", "--no-env-resolution", "--format", "json",
))


def scenario(legacy, conflict=False, invalid=None):
    project = f"auth-upgrade-test-{uuid.uuid4().hex[:10]}"
    network = f"{project}-network"
    seed_container = f"{project}-old-mongo"
    selected = ("postgres", "central-auth-mongodb", "central-auth")
    config = {"services": {name: copy.deepcopy(production["services"][name]) for name in selected}}
    volume_keys = ("postgres-data", "central-auth-mongo-data", "central-auth-migration")
    config["volumes"] = {name: {"name": f"{project}-{name}"} for name in volume_keys}
    config["networks"] = {"unicron-network": {"name": network}}
    for name, service in config["services"].items():
        for key in ("build", "env_file", "container_name", "ports", "pull_policy"):
            service.pop(key, None)
        service["restart"] = "no"
        service["healthcheck"]["interval"] = "1s"
    auth = config["services"]["central-auth"]
    auth["image"] = IMAGE
    auth["environment"].update({
        "CENTRAL_AUTH_POSTGRES_SCHEMA": "ComposeAuth_test",
        "CENTRAL_ADMIN_PASSWORD": "Stale-Bootstrap-Password1!",
        "CENTRAL_AUTH_BASE_URL": "http://central-auth:3020",
    })
    if invalid == "database":
        auth["environment"]["LEGACY_MONGODB_DB_NAME"] = "wrong_database"
    mongo_volume = config["volumes"]["central-auth-mongo-data"]["name"]

    with tempfile.TemporaryDirectory(prefix=project) as directory:
        path = Path(directory) / "compose.json"
        path.write_text(json.dumps(config))
        compose = ("docker", "compose", "-p", project, "-f", str(path))

        def node(script):
            return run("docker", "run", "--rm", "--network", network,
                       "--entrypoint", "node", IMAGE, "--input-type=module", "-e", script)

        def login(password, expected):
            node(f"""
                const r = await fetch('http://central-auth:3020/api/auth/sign-in/username', {{
                  method: 'POST', headers: {{'content-type': 'application/json'}},
                  body: JSON.stringify({{username: 'admin', password: {json.dumps(password)}}})
                }});
                if (r.status !== {expected}) throw new Error('Unexpected login status: ' + r.status);
                if (r.ok) {{
                  const cookie = r.headers.get('set-cookie').split(';')[0];
                  const profile = await fetch('http://central-auth:3020/api/v1/profile', {{headers: {{cookie}}}});
                  if (!profile.ok) throw new Error('Authenticated profile failed: ' + profile.status);
                }}
            """)

        def assert_mongo_idle():
            output = run(*compose, "exec", "-T", "central-auth-mongodb", "sh", "-c", "cat /proc/1/comm")
            assert output == "sleep", output

        try:
            run(*compose, "up", "-d", "--wait", "--wait-timeout", "120", "postgres")
            if conflict:
                run(*compose, "up", "-d", "--wait", "--wait-timeout", "180", "central-auth")
                login("Stale-Bootstrap-Password1!", 200)
                run(*compose, "stop", "central-auth", "central-auth-mongodb")
            if legacy:
                run("docker", "volume", "create", mongo_volume)
                run("docker", "run", "-d", "--name", seed_container, "--network", network,
                    "-v", f"{mongo_volume}:/data/db", "-e", "MONGO_INITDB_ROOT_USERNAME=root",
                    "-e", "MONGO_INITDB_ROOT_PASSWORD=password", "mongo:7")
                node(f"""
                    import {{ MongoClient, ObjectId }} from 'mongodb';
                    import {{ hashPassword }} from 'better-auth/crypto';
                    const client = new MongoClient('mongodb://root:password@{seed_container}:27017/?authSource=admin', {{serverSelectionTimeoutMS: 60000}});
                    await client.connect();
                    const db = client.db('unicron_central_auth');
                    const id = new ObjectId(); const now = new Date();
                    await db.collection('user').insertOne({{_id: id, username: 'admin', displayUsername: 'admin', name: 'admin', email: 'admin@local.unicron.invalid', emailVerified: true, requiresPasswordChange: false, createdAt: now, updatedAt: now}});
                    if ({json.dumps(invalid != 'credential')}) await db.collection('account').insertOne({{_id: new ObjectId(), userId: id, accountId: String(id), providerId: 'credential', password: await hashPassword('Changed-Legacy-Password1!'), createdAt: now, updatedAt: now}});
                    await db.collection('session').insertOne({{userId: id, token: 'old-session-must-not-migrate'}});
                    await client.close();
                """)
                run("docker", "rm", "-f", seed_container)

            if conflict or invalid:
                result = subprocess.run((*compose, "up", "-d", "--wait", "--wait-timeout", "45", "central-auth"), capture_output=True, text=True)
                assert result.returncode != 0, "Unsafe migration must block startup"
                expected_error = "different administrators" if conflict else "exactly one administrator" if invalid == "database" else "no password credential"
                assert expected_error in run(*compose, "logs", "central-auth")
                run(*compose, "exec", "-T", "central-auth-mongodb", "test", "!", "-e", "/migration/completed")
                print(f"PASS: {expected_error} blocks startup without marking migration complete", flush=True)
                return

            run(*compose, "up", "-d", "--wait", "--wait-timeout", "180", "central-auth")
            password = "Changed-Legacy-Password1!" if legacy else "Stale-Bootstrap-Password1!"
            login(password, 200)
            login("Stale-Bootstrap-Password1!" if legacy else "Wrong-Password1!", 401)
            if not legacy:
                assert_mongo_idle()
            else:
                # Simulate a crash after the database commit but before persisting the marker.
                run(*compose, "exec", "-T", "central-auth", "rm", "/migration/completed")
                run(*compose, "up", "-d", "--force-recreate", "--wait", "--wait-timeout", "180", "central-auth-mongodb", "central-auth")
                login(password, 200)
            # Recreate both containers to prove persisted migration state, not in-memory state.
            run(*compose, "up", "-d", "--force-recreate", "--wait", "--wait-timeout", "180", "central-auth-mongodb", "central-auth")
            assert_mongo_idle()
            login(password, 200)
            login("Stale-Bootstrap-Password1!" if legacy else "Wrong-Password1!", 401)
            schema = run(*compose, "exec", "-T", "postgres", "psql", "-U", auth["environment"]["POSTGRES_USER"],
                         "-d", auth["environment"]["POSTGRES_DB"], "-Atc",
                         "SELECT count(*) FROM pg_tables WHERE schemaname = 'ComposeAuth_test' AND tablename IN ('user','account','session','verification')")
            assert schema == "4", schema
            print(f"PASS: {'legacy migration' if legacy else 'fresh install'}, login, rejected password, profile, restart, mixed-case schema, idle MongoDB", flush=True)
        finally:
            run("docker", "rm", "-f", seed_container, check=False)
            run(*compose, "down", "-v", "--remove-orphans")


scenario(False)
scenario(True)
scenario(True, conflict=True)
scenario(True, invalid="database")
scenario(True, invalid="credential")
