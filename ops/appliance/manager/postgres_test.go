package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestCopyPostgresSeedClusterCopiesSeed(t *testing.T) {
	tmpDir := t.TempDir()
	seedDir := filepath.Join(tmpDir, "seed")
	pgData := filepath.Join(tmpDir, "postgres")
	writePostgresSeedFixture(t, seedDir)
	if err := os.Mkdir(pgData, 0o700); err != nil {
		t.Fatal(err)
	}

	backupPath, err := copyPostgresSeedCluster(pgData, seedDir, time.Date(2026, 5, 9, 12, 0, 0, 0, time.UTC))
	if err != nil {
		t.Fatal(err)
	}
	if backupPath != "" {
		t.Fatalf("backupPath = %q, want empty", backupPath)
	}
	assertFileContent(t, filepath.Join(pgData, "PG_VERSION"), "15\n")
	assertFileContent(t, filepath.Join(pgData, "base", "fixture"), "seed data\n")
	info, err := os.Stat(pgData)
	if err != nil {
		t.Fatal(err)
	}
	if got := info.Mode().Perm(); got != 0o700 {
		t.Fatalf("pgData mode = %o, want 700", got)
	}
}

func TestCopyPostgresSeedClusterBacksUpPartialDirectory(t *testing.T) {
	tmpDir := t.TempDir()
	seedDir := filepath.Join(tmpDir, "seed")
	pgData := filepath.Join(tmpDir, "postgres")
	writePostgresSeedFixture(t, seedDir)
	if err := os.MkdirAll(filepath.Join(pgData, "base"), 0o700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(pgData, "partial"), []byte("failed initdb\n"), 0o600); err != nil {
		t.Fatal(err)
	}

	now := time.Date(2026, 5, 9, 12, 0, 0, 0, time.UTC)
	backupPath, err := copyPostgresSeedCluster(pgData, seedDir, now)
	if err != nil {
		t.Fatal(err)
	}
	wantBackup := filepath.Join(tmpDir, "postgres.bootstrap-backup-20260509T120000Z")
	if backupPath != wantBackup {
		t.Fatalf("backupPath = %q, want %q", backupPath, wantBackup)
	}
	assertFileContent(t, filepath.Join(backupPath, "partial"), "failed initdb\n")
	assertFileContent(t, filepath.Join(pgData, "PG_VERSION"), "15\n")
	if _, err := os.Stat(filepath.Join(pgData, "partial")); !os.IsNotExist(err) {
		t.Fatalf("partial file remained in copied seed dir; stat err = %v", err)
	}
}

func TestReconcileInitializedPostgresSkipsMissingCluster(t *testing.T) {
	tmpDir := t.TempDir()
	cfg := RuntimeConfig{
		DataDir:      tmpDir,
		PostgresUser: "unicron",
		PostgresDB:   "unicron",
	}

	if err := reconcileInitializedPostgres(cfg, filepath.Join(tmpDir, "postgres"), filepath.Join(tmpDir, "socket")); err != nil {
		t.Fatalf("reconcileInitializedPostgres() = %v, want nil", err)
	}
}

func TestPreparePostgresRuntimeDirsNormalizesModes(t *testing.T) {
	tmpDir := t.TempDir()
	pgData := filepath.Join(tmpDir, "postgres")
	socketDir := filepath.Join(tmpDir, "socket")
	if err := os.MkdirAll(pgData, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(socketDir, 0o755); err != nil {
		t.Fatal(err)
	}

	if err := preparePostgresRuntimeDirs(pgData, socketDir); err != nil {
		t.Fatal(err)
	}

	assertDirMode(t, pgData, 0o700)
	assertDirMode(t, socketDir, 0o775)
}

func TestPostgresSQLQuoting(t *testing.T) {
	if got, want := postgresQuoteIdentifier(`role"name`), `"role""name"`; got != want {
		t.Fatalf("postgresQuoteIdentifier() = %q, want %q", got, want)
	}
	if got, want := postgresQuoteLiteral(`pass'word`), `'pass''word'`; got != want {
		t.Fatalf("postgresQuoteLiteral() = %q, want %q", got, want)
	}

	roleSQL := postgresRoleBootstrapSQL(`role'"name`, `pa'ss`)
	for _, want := range []string{
		`rolname = 'role''"name'`,
		`CREATE ROLE "role'""name" LOGIN`,
		`ALTER ROLE "role'""name" WITH LOGIN PASSWORD 'pa''ss'`,
	} {
		if !strings.Contains(roleSQL, want) {
			t.Fatalf("role SQL missing %q: %s", want, roleSQL)
		}
	}

	if got, want := postgresDatabaseExistsSQL(`db'name`), `SELECT 1 FROM pg_catalog.pg_database WHERE datname = 'db''name'`; got != want {
		t.Fatalf("postgresDatabaseExistsSQL() = %q, want %q", got, want)
	}
	if got, want := postgresDatabaseOwnerSQL(`db"name`, `role"name`), `ALTER DATABASE "db""name" OWNER TO "role""name"`; got != want {
		t.Fatalf("postgresDatabaseOwnerSQL() = %q, want %q", got, want)
	}
}

func writePostgresSeedFixture(t *testing.T, seedDir string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Join(seedDir, "base"), 0o700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(seedDir, "PG_VERSION"), []byte("15\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(seedDir, "base", "fixture"), []byte("seed data\n"), 0o600); err != nil {
		t.Fatal(err)
	}
}

func assertFileContent(t *testing.T, path, want string) {
	t.Helper()
	body, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if got := string(body); got != want {
		t.Fatalf("%s = %q, want %q", path, got, want)
	}
}

func assertDirMode(t *testing.T, path string, want os.FileMode) {
	t.Helper()
	info, err := os.Stat(path)
	if err != nil {
		t.Fatal(err)
	}
	if got := info.Mode().Perm(); got != want {
		t.Fatalf("%s mode = %o, want %o", path, got, want)
	}
}
