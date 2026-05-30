package main

import (
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

type identity struct {
	uid  int
	gid  int
	home string
}

func ensureDir(path string, mode os.FileMode) error {
	if err := os.MkdirAll(path, mode); err != nil {
		return err
	}
	return os.Chmod(path, mode)
}

func writeFilePrivate(path, value string) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	tmp := path + ".tmp"
	if err := os.WriteFile(tmp, []byte(value), 0o600); err != nil {
		return err
	}
	if err := os.Rename(tmp, path); err != nil {
		_ = os.Remove(tmp)
		return err
	}
	return os.Chmod(path, 0o600)
}

func fileExists(path string) bool {
	info, err := os.Stat(path)
	return err == nil && !info.IsDir()
}

func fileNonEmpty(path string) bool {
	info, err := os.Stat(path)
	return err == nil && !info.IsDir() && info.Size() > 0
}

func copyFile(src, dst string, mode os.FileMode) error {
	in, err := os.Open(src)
	if err != nil {
		return err
	}
	defer in.Close()
	if err := os.MkdirAll(filepath.Dir(dst), 0o755); err != nil {
		return err
	}
	tmp := dst + ".tmp"
	out, err := os.OpenFile(tmp, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, mode)
	if err != nil {
		return err
	}
	_, copyErr := io.Copy(out, in)
	closeErr := out.Close()
	if copyErr != nil {
		_ = os.Remove(tmp)
		return copyErr
	}
	if closeErr != nil {
		_ = os.Remove(tmp)
		return closeErr
	}
	if err := os.Chmod(tmp, mode); err != nil {
		_ = os.Remove(tmp)
		return err
	}
	if err := os.Rename(tmp, dst); err != nil {
		_ = os.Remove(tmp)
		return err
	}
	return nil
}

func touch(path string) error {
	now := time.Now()
	if fileExists(path) {
		return os.Chtimes(path, now, now)
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	f, err := os.OpenFile(path, os.O_CREATE|os.O_RDWR, 0o664)
	if err != nil {
		return err
	}
	return f.Close()
}

func lookupIdentity(userName, groupName string) (identity, error) {
	uid, primaryGID, home, err := lookupPasswd(userName)
	if err != nil {
		return identity{}, err
	}
	gid := primaryGID
	if groupName != "" {
		if groupGID, err := lookupGroup(groupName); err == nil {
			gid = groupGID
		} else {
			return identity{}, err
		}
	}
	return identity{uid: uid, gid: gid, home: home}, nil
}

func lookupPasswd(name string) (uid int, gid int, home string, err error) {
	content, err := os.ReadFile("/etc/passwd")
	if err != nil {
		return 0, 0, "", err
	}
	for _, line := range strings.Split(string(content), "\n") {
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		fields := strings.Split(line, ":")
		if len(fields) < 4 || fields[0] != name {
			continue
		}
		uid, err := strconv.Atoi(fields[2])
		if err != nil {
			return 0, 0, "", err
		}
		gid, err := strconv.Atoi(fields[3])
		if err != nil {
			return 0, 0, "", err
		}
		return uid, gid, fields[5], nil
	}
	return 0, 0, "", fmt.Errorf("user %q not found", name)
}

func lookupGroup(name string) (int, error) {
	content, err := os.ReadFile("/etc/group")
	if err != nil {
		return 0, err
	}
	for _, line := range strings.Split(string(content), "\n") {
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		fields := strings.Split(line, ":")
		if len(fields) < 3 || fields[0] != name {
			continue
		}
		return strconv.Atoi(fields[2])
	}
	return 0, fmt.Errorf("group %q not found", name)
}

func chownR(owner string, paths ...string) {
	parts := strings.Split(owner, ":")
	userName := parts[0]
	groupName := ""
	if len(parts) > 1 {
		groupName = parts[1]
	}
	id, err := lookupIdentity(userName, groupName)
	if err != nil {
		logf("APPLIANCE-ENTRY", "Skipping chown %s: %v", owner, err)
		return
	}
	for _, root := range paths {
		_ = filepath.WalkDir(root, func(path string, d os.DirEntry, err error) error {
			if err != nil {
				return filepath.SkipDir
			}
			if chownErr := os.Lchown(path, id.uid, id.gid); chownErr != nil && !errors.Is(chownErr, os.ErrPermission) {
				return nil
			}
			return nil
		})
	}
}

func chownPath(owner, path string) {
	parts := strings.Split(owner, ":")
	userName := parts[0]
	groupName := ""
	if len(parts) > 1 {
		groupName = parts[1]
	}
	id, err := lookupIdentity(userName, groupName)
	if err != nil {
		return
	}
	_ = os.Chown(path, id.uid, id.gid)
}
