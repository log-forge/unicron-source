package main

import (
	"context"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
	"time"
)

const (
	postgresBinDir  = "/usr/lib/postgresql/15/bin"
	postgresSeedDir = "/usr/local/share/unicron/postgres-seed"
)

func bootstrapPostgresFromSeed(cfg RuntimeConfig, pgData, socketDir string) error {
	logf("APPLIANCE:postgres", "Bootstrapping Postgres data directory from image seed")
	backupPath, err := copyPostgresSeedCluster(pgData, postgresSeedDir, time.Now())
	if err != nil {
		return err
	}
	if backupPath != "" {
		logf("APPLIANCE:postgres", "Moved partial Postgres data directory to %s", backupPath)
	}
	chownR("postgres:postgres", pgData)
	if err := ensurePostgresRoleAndDatabase(cfg, pgData, socketDir); err != nil {
		return err
	}
	return nil
}

func reconcileInitializedPostgres(cfg RuntimeConfig, pgData, socketDir string) error {
	if !fileNonEmpty(filepath.Join(pgData, "PG_VERSION")) {
		return nil
	}
	if err := preparePostgresRuntimeDirs(pgData, socketDir); err != nil {
		return err
	}
	logf("APPLIANCE:postgres", "Reconciling Postgres role credentials")
	if err := ensurePostgresRoleAndDatabase(cfg, pgData, socketDir); err != nil {
		return fmt.Errorf("reconcile Postgres role credentials: %w", err)
	}
	return nil
}

func preparePostgresRuntimeDirs(pgData, socketDir string) error {
	if err := ensureDir(pgData, 0o700); err != nil {
		return err
	}
	if err := ensureDir(socketDir, 0o775); err != nil {
		return err
	}
	chownR("postgres:postgres", pgData, socketDir)
	return nil
}

func copyPostgresSeedCluster(pgData, seedDir string, now time.Time) (string, error) {
	if !fileNonEmpty(filepath.Join(seedDir, "PG_VERSION")) {
		return "", fmt.Errorf("Postgres seed cluster is missing %s", filepath.Join(seedDir, "PG_VERSION"))
	}
	if fileNonEmpty(filepath.Join(pgData, "PG_VERSION")) {
		return "", nil
	}

	nonEmpty, err := directoryNonEmpty(pgData)
	if err != nil {
		return "", err
	}
	backupPath := ""
	if nonEmpty {
		backupPath = nextPostgresBackupPath(pgData, now)
		if err := os.Rename(pgData, backupPath); err != nil {
			return "", fmt.Errorf("backup partial Postgres data directory: %w", err)
		}
	}
	if err := os.MkdirAll(pgData, 0o700); err != nil {
		return "", err
	}
	if err := os.Chmod(pgData, 0o700); err != nil {
		return "", err
	}
	if err := copyDirectoryContents(seedDir, pgData); err != nil {
		return "", err
	}
	if err := os.Chmod(pgData, 0o700); err != nil {
		return "", err
	}
	return backupPath, nil
}

func directoryNonEmpty(path string) (bool, error) {
	entries, err := os.ReadDir(path)
	if os.IsNotExist(err) {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	return len(entries) > 0, nil
}

func nextPostgresBackupPath(pgData string, now time.Time) string {
	base := fmt.Sprintf("%s.bootstrap-backup-%s", pgData, now.UTC().Format("20060102T150405Z"))
	candidate := base
	for suffix := 1; ; suffix++ {
		if _, err := os.Lstat(candidate); os.IsNotExist(err) {
			return candidate
		}
		candidate = fmt.Sprintf("%s.%d", base, suffix)
	}
}

func copyDirectoryContents(src, dst string) error {
	return filepath.WalkDir(src, func(path string, entry os.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		rel, err := filepath.Rel(src, path)
		if err != nil {
			return err
		}
		if rel == "." {
			return nil
		}
		target := filepath.Join(dst, rel)
		info, err := entry.Info()
		if err != nil {
			return err
		}
		if entry.Type()&os.ModeSymlink != 0 {
			linkTarget, err := os.Readlink(path)
			if err != nil {
				return err
			}
			if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
				return err
			}
			return os.Symlink(linkTarget, target)
		}
		if entry.IsDir() {
			if err := os.MkdirAll(target, info.Mode().Perm()); err != nil {
				return err
			}
			return os.Chmod(target, info.Mode().Perm())
		}
		if !entry.Type().IsRegular() {
			return nil
		}
		return copyRegularFile(path, target, info.Mode().Perm())
	})
}

func copyRegularFile(src, dst string, mode os.FileMode) error {
	in, err := os.Open(src)
	if err != nil {
		return err
	}
	defer in.Close()
	if err := os.MkdirAll(filepath.Dir(dst), 0o755); err != nil {
		return err
	}
	out, err := os.OpenFile(dst, os.O_WRONLY|os.O_CREATE|os.O_EXCL, mode)
	if err != nil {
		return err
	}
	_, copyErr := io.Copy(out, in)
	closeErr := out.Close()
	if copyErr != nil {
		_ = os.Remove(dst)
		return copyErr
	}
	if closeErr != nil {
		_ = os.Remove(dst)
		return closeErr
	}
	return os.Chmod(dst, mode)
}

func ensurePostgresRoleAndDatabase(cfg RuntimeConfig, pgData, socketDir string) (err error) {
	ctx, cancel := context.WithTimeout(context.Background(), 90*time.Second)
	defer cancel()

	cmd, err := startTemporaryPostgres(pgData, socketDir)
	if err != nil {
		return err
	}
	defer func() {
		if stopErr := stopTemporaryPostgres(cmd, 20*time.Second); err == nil && stopErr != nil {
			err = stopErr
		}
	}()

	if err := waitForTemporaryPostgres(ctx, socketDir); err != nil {
		return err
	}
	if err := runPostgresSQL(ctx, socketDir, "postgres", postgresRoleBootstrapSQL(cfg.PostgresUser, os.Getenv("POSTGRES_PASSWORD")), false); err != nil {
		return fmt.Errorf("bootstrap Postgres role %q: %w", cfg.PostgresUser, err)
	}
	exists, err := postgresDatabaseExists(ctx, socketDir, cfg.PostgresDB)
	if err != nil {
		return err
	}
	if !exists {
		if err := runCommand(ctx, filepath.Join(postgresBinDir, "createdb"), []string{
			"-h", socketDir,
			"-p", "5432",
			"-U", "postgres",
			"--owner=" + cfg.PostgresUser,
			"--",
			cfg.PostgresDB,
		}, postgresCommandOptions(false)); err != nil {
			return fmt.Errorf("create Postgres database %q: %w", cfg.PostgresDB, err)
		}
	}
	if err := runPostgresSQL(ctx, socketDir, "postgres", postgresDatabaseOwnerSQL(cfg.PostgresDB, cfg.PostgresUser), false); err != nil {
		return fmt.Errorf("assign Postgres database %q owner: %w", cfg.PostgresDB, err)
	}
	return nil
}

func startTemporaryPostgres(pgData, socketDir string) (*exec.Cmd, error) {
	id, err := lookupIdentity("postgres", "postgres")
	if err != nil {
		return nil, err
	}
	cmd := exec.Command(filepath.Join(postgresBinDir, "postgres"),
		"-D", pgData,
		"-c", "listen_addresses=127.0.0.1",
		"-c", "port=5432",
		"-c", "unix_socket_directories="+socketDir,
	)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	cmd.Env = envForIdentity(os.Environ(), "postgres", id)
	cmd.SysProcAttr = &syscall.SysProcAttr{
		Credential: &syscall.Credential{Uid: uint32(id.uid), Gid: uint32(id.gid)},
		Setpgid:    true,
	}
	if err := cmd.Start(); err != nil {
		return nil, err
	}
	return cmd, nil
}

func stopTemporaryPostgres(cmd *exec.Cmd, grace time.Duration) error {
	if cmd == nil || cmd.Process == nil {
		return nil
	}
	done := make(chan error, 1)
	go func() {
		done <- cmd.Wait()
	}()
	_ = syscall.Kill(-cmd.Process.Pid, syscall.SIGTERM)
	select {
	case err := <-done:
		return err
	case <-time.After(grace):
		_ = syscall.Kill(-cmd.Process.Pid, syscall.SIGKILL)
		return <-done
	}
}

func waitForTemporaryPostgres(ctx context.Context, socketDir string) error {
	ticker := time.NewTicker(time.Second)
	defer ticker.Stop()
	for {
		if err := runPostgresSQL(ctx, socketDir, "postgres", "SELECT 1", true); err == nil {
			return nil
		}
		select {
		case <-ctx.Done():
			return fmt.Errorf("timed out waiting for temporary Postgres: %w", ctx.Err())
		case <-ticker.C:
		}
	}
}

func postgresDatabaseExists(ctx context.Context, socketDir, database string) (bool, error) {
	output, err := postgresSQLOutput(ctx, socketDir, "postgres", postgresDatabaseExistsSQL(database))
	if err != nil {
		return false, fmt.Errorf("check Postgres database %q: %w", database, err)
	}
	return strings.TrimSpace(output) == "1", nil
}

func runPostgresSQL(ctx context.Context, socketDir, database, sql string, quiet bool) error {
	return runCommand(ctx, filepath.Join(postgresBinDir, "psql"), postgresSQLArgs(socketDir, database, sql, false), postgresCommandOptions(quiet))
}

func postgresSQLOutput(ctx context.Context, socketDir, database, sql string) (string, error) {
	return commandOutput(ctx, filepath.Join(postgresBinDir, "psql"), postgresSQLArgs(socketDir, database, sql, true), postgresCommandOptions(false))
}

func postgresSQLArgs(socketDir, database, sql string, tuplesOnly bool) []string {
	args := []string{
		"-X",
		"-v", "ON_ERROR_STOP=1",
		"-h", socketDir,
		"-p", "5432",
		"-U", "postgres",
		"-d", database,
	}
	if tuplesOnly {
		args = append(args, "-A", "-t")
	}
	return append(args, "-c", sql)
}

func postgresCommandOptions(quiet bool) commandOptions {
	return commandOptions{user: "postgres", group: "postgres", quiet: quiet}
}

func postgresRoleBootstrapSQL(user, password string) string {
	userIdentifier := postgresQuoteIdentifier(user)
	return fmt.Sprintf(`DO $unicron_role$
BEGIN
	IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = %s) THEN
		CREATE ROLE %s LOGIN;
	END IF;
END
$unicron_role$;
ALTER ROLE %s WITH LOGIN PASSWORD %s;`,
		postgresQuoteLiteral(user),
		userIdentifier,
		userIdentifier,
		postgresQuoteLiteral(password),
	)
}

func postgresDatabaseExistsSQL(database string) string {
	return fmt.Sprintf("SELECT 1 FROM pg_catalog.pg_database WHERE datname = %s", postgresQuoteLiteral(database))
}

func postgresDatabaseOwnerSQL(database, owner string) string {
	return fmt.Sprintf("ALTER DATABASE %s OWNER TO %s", postgresQuoteIdentifier(database), postgresQuoteIdentifier(owner))
}

func postgresQuoteIdentifier(identifier string) string {
	return `"` + strings.ReplaceAll(identifier, `"`, `""`) + `"`
}

func postgresQuoteLiteral(value string) string {
	return `'` + strings.ReplaceAll(value, `'`, `''`) + `'`
}
