package config

import (
	"os"
	"strconv"
	"time"
)

type Config struct {
	Port         int
	StorageRoot  string
	WorkerToken  string
	LeaseTTL     time.Duration
	PollInterval time.Duration
	Backend      string
}

func LoadConfig() Config {
	port := 8081
	if portStr := os.Getenv("ORCHESTRATOR_PORT"); portStr != "" {
		if p, err := strconv.Atoi(portStr); err == nil {
			port = p
		}
	}

	storageRoot := os.Getenv("ORCHESTRATOR_STORAGE_ROOT")
	if storageRoot == "" {
		storageRoot = "./data/adgo_store"
	}

	token := os.Getenv("ORCHESTRATOR_WORKER_TOKEN")
	if token == "" {
		token = "adgo-dev-token"
	}

	backend := os.Getenv("ORCHESTRATOR_BACKEND")
	if backend == "" {
		backend = "pebble"
	}

	return Config{
		Port:         port,
		StorageRoot:  storageRoot,
		WorkerToken:  token,
		LeaseTTL:     30 * time.Second,
		PollInterval: 100 * time.Millisecond,
		Backend:      backend,
	}
}
