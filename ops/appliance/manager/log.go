package main

import (
	"fmt"
	"os"
	"time"
)

func logf(component, format string, args ...any) {
	msg := fmt.Sprintf(format, args...)
	fmt.Fprintf(os.Stdout, "[%s] [%s] %s\n", time.Now().Format("2006-01-02 15:04:05"), component, msg)
}
