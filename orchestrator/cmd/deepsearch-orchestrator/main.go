package main

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/Homiakus/axiom/adgo"
	"github.com/Homiakus/deepsearch/orchestrator/internal/config"
	"github.com/Homiakus/deepsearch/orchestrator/internal/plan"
	"github.com/Homiakus/deepsearch/orchestrator/internal/server"
)

func main() {
	cfg := config.LoadConfig()
	log.Printf("[Orchestrator] Starting DeepSearch Axiom ADGO Orchestrator on :%d...", cfg.Port)

	compiledPlan, err := plan.CompileResearchPlan()
	if err != nil {
		log.Fatalf("[Orchestrator] Failed to compile research plan: %v", err)
	}
	log.Printf("[Orchestrator] Plan %q compiled successfully (digest: %s)", compiledPlan.ID, compiledPlan.Digest)

	registry := adgo.NewRegistry()

	prodCfg := adgo.ProductionConfig{
		Backend:             adgo.BackendPebble,
		Root:                cfg.StorageRoot,
		LeaseTTL:            cfg.LeaseTTL,
		PollInterval:        cfg.PollInterval,
		CoordinatorInterval: 50 * time.Millisecond,
		MaxLeaseRecoveries:  5,
		Router:              adgo.DefaultRouterConfig(),
	}

	if cfg.Backend == "memory" {
		prodCfg.Backend = adgo.BackendMemory
	}

	prod, err := adgo.OpenProduction(compiledPlan, registry, prodCfg)
	if err != nil {
		log.Fatalf("[Orchestrator] Failed to open ADGO production runtime: %v", err)
	}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	go func() {
		if err := prod.Engine.RunCoordinator(ctx); err != nil && err != context.Canceled {
			log.Printf("[Orchestrator] ADGO coordinator loop ended: %v", err)
		}
	}()
	log.Printf("[Orchestrator] ADGO coordinator active with backend %s", prodCfg.Backend)

	workerHandler, err := server.NewWorkerServerHandler(prod.Engine, cfg.WorkerToken)
	if err != nil {
		log.Fatalf("[Orchestrator] Failed to create worker HTTP handler: %v", err)
	}

	apiServer := server.NewAPIServer(prod.Engine, prod.Store, workerHandler)

	httpServer := &http.Server{
		Addr:         fmt.Sprintf(":%d", cfg.Port),
		Handler:      apiServer,
		ReadTimeout:  30 * time.Second,
		WriteTimeout: 30 * time.Second,
	}

	go func() {
		if err := httpServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("[Orchestrator] HTTP server error: %v", err)
		}
	}()
	log.Printf("[Orchestrator] Ready to accept API and remote worker requests on :%d", cfg.Port)

	// Graceful shutdown
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, os.Interrupt, syscall.SIGTERM)
	<-sigChan

	log.Println("[Orchestrator] Shutting down...")
	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer shutdownCancel()
	httpServer.Shutdown(shutdownCtx)
	log.Println("[Orchestrator] Stopped gracefully.")
}
