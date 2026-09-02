package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/Homiakus/SncSinCore/epmemory"
	"github.com/Homiakus/deepsearch/orchestrator/internal/epistemic"
	"github.com/Homiakus/deepsearch/orchestrator/internal/server"
)

func main() {
	port := flag.Int("port", 8989, "HTTP listen port")
	host := flag.String("host", "127.0.0.1", "HTTP listen host")
	flag.Parse()

	addr := fmt.Sprintf("%s:%d", *host, *port)

	initialCorpus := epmemory.Corpus{
		Version: "v1.0",
		Nodes:   []epmemory.NodeInput{},
		Edges:   []epmemory.EdgeInput{},
	}

	engine, err := epistemic.NewEngine(epistemic.Config{
		DefaultMaxLatencyMS: 2000,
		DefaultMaxTokens:    2048,
	}, initialCorpus)
	if err != nil {
		log.Fatalf("failed to initialize epistemic engine: %v", err)
	}

	srvHandler := server.NewEpistemicServer(engine)
	httpServer := &http.Server{
		Addr:              addr,
		Handler:           srvHandler,
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       10 * time.Second,
		WriteTimeout:      15 * time.Second,
		IdleTimeout:       60 * time.Second,
	}

	go func() {
		log.Printf("Starting SncSinCore Epistemic Memory Daemon on %s", addr)
		if err := httpServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("HTTP server error: %v", err)
		}
	}()

	// Graceful shutdown on SIGINT / SIGTERM
	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt, syscall.SIGTERM)
	<-stop

	log.Println("Shutting down Epistemic Memory Daemon...")
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	if err := httpServer.Shutdown(ctx); err != nil {
		log.Printf("Shutdown error: %v", err)
	}
	log.Println("Epistemic Memory Daemon stopped cleanly.")
}
