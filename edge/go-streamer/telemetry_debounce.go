package main

import (
	"sync"
	"time"
)

// ConfigDebouncer aggregates rapid config change triggers into a single callback
// invocation after the specified delay. Each call to Trigger() resets the timer,
// so the callback only fires after a period of inactivity (3 seconds by default).
type ConfigDebouncer struct {
	mu       sync.Mutex
	timer    *time.Timer
	delay    time.Duration
	callback func()
}

// NewConfigDebouncer creates a new debouncer with the given delay and callback.
// The callback fires once after `delay` has elapsed since the last Trigger() call.
func NewConfigDebouncer(delay time.Duration, callback func()) *ConfigDebouncer {
	return &ConfigDebouncer{
		delay:    delay,
		callback: callback,
	}
}

// Trigger resets the debounce timer. If called multiple times within the delay window,
// only the last trigger results in the callback firing.
func (d *ConfigDebouncer) Trigger() {
	d.mu.Lock()
	defer d.mu.Unlock()

	// Stop existing timer if running
	if d.timer != nil {
		d.timer.Stop()
	}

	// Start new timer
	d.timer = time.AfterFunc(d.delay, d.callback)
}

// Stop cancels any pending debounced callback. Used for graceful shutdown.
func (d *ConfigDebouncer) Stop() {
	d.mu.Lock()
	defer d.mu.Unlock()

	if d.timer != nil {
		d.timer.Stop()
		d.timer = nil
	}
}
