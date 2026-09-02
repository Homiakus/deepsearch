package epistemic

import (
	"context"
	"testing"
	"time"

	"github.com/Homiakus/SncSinCore/epmemory"
	"github.com/Homiakus/SncSinCore/memory"
)

func sampleCorpus() epmemory.Corpus {
	return epmemory.Corpus{
		Version: "v1.0",
		Nodes: []epmemory.NodeInput{
			{
				ID:              "claim:caffeine-alertness",
				Kind:            epmemory.KindProposition,
				Text:            "Caffeine increases alertness in sleep-deprived adults.",
				Belief:          epmemory.Float64(0.92),
				EvidenceQuality: epmemory.Float64(0.88),
				Context:         "adult-human",
				Scope:           "public",
			},
			{
				ID:                "evidence:rct-trial-2024",
				Kind:              epmemory.KindEvidence,
				Text:              "Double-blind RCT (n=120) confirmed reaction time improvement.",
				Belief:            epmemory.Float64(0.96),
				EvidenceQuality:   epmemory.Float64(0.95),
				Context:           "adult-human",
				Scope:             "public",
				ProvenanceCluster: "trial-2024",
			},
		},
		Edges: []epmemory.EdgeInput{
			{
				From:     "claim:caffeine-alertness",
				To:       "evidence:rct-trial-2024",
				Relation: epmemory.RelEvidenceFor,
			},
		},
	}
}

func TestEpistemicEngineLifecycleAndQuery(t *testing.T) {
	ctx := context.Background()
	engine, err := NewEngine(Config{
		DefaultMaxLatencyMS: 1500,
		DefaultMaxTokens:    1024,
	}, sampleCorpus())
	if err != nil {
		t.Fatalf("failed to create engine: %v", err)
	}

	if engine.NodeCount() != 2 {
		t.Fatalf("expected 2 nodes, got %d", engine.NodeCount())
	}

	req := epmemory.QueryRequest{
		Text:          "Does caffeine improve alertness?",
		Intent:        epmemory.IntentFactual,
		Targets:       []string{"claim:caffeine-alertness"},
		Context:       "adult-human",
		AllowedScopes: []string{"public"},
		StrictContext: true,
		Requirements: []epmemory.RequirementInput{
			{
				ID:              "req-alertness",
				Kind:            epmemory.ReqFact,
				Text:            "Verify evidence for alertness increase",
				Criticality:     epmemory.Float64(1.0),
				MinimumCoverage: epmemory.Float64(0.80),
				Targets:         []string{"claim:caffeine-alertness"},
			},
		},
	}

	art, err := engine.Query(ctx, req, memory.Budget{
		MaxLatency:       1 * time.Second,
		MaxContextTokens: 2048,
	})
	if err != nil {
		t.Fatalf("query failed: %v", err)
	}

	if art.Status != "complete" && art.Status != "partial" {
		t.Fatalf("unexpected artifact status: %s", art.Status)
	}

	if art.Digest == "" {
		t.Fatal("artifact must contain SHA-256 digest")
	}

	report, err := engine.AuditArtifact(art, req)
	if err != nil {
		t.Fatalf("audit failed: %v", err)
	}

	if report.Schema == "" {
		t.Fatal("expected report with schema")
	}
}

func TestEpistemicEngineIngestAndConcurrency(t *testing.T) {
	ctx := context.Background()
	engine, err := NewEngine(Config{}, sampleCorpus())
	if err != nil {
		t.Fatalf("failed to create engine: %v", err)
	}

	// Concurrent querying and ingestion
	done := make(chan struct{})
	go func() {
		defer close(done)
		for i := 0; i < 10; i++ {
			req := epmemory.QueryRequest{
				Text:    "test query",
				Targets: []string{"claim:caffeine-alertness"},
			}
			_, _ = engine.Query(ctx, req, memory.Budget{MaxLatency: 500 * time.Millisecond})
		}
	}()

	newNodes := []epmemory.NodeInput{
		{
			ID:      "claim:caffeine-metabolism",
			Kind:    epmemory.KindProposition,
			Text:    "Caffeine is metabolized by CYP1A2 in the liver.",
			Context: "adult-human",
			Scope:   "public",
		},
	}
	err = engine.IngestNodes(ctx, newNodes, nil)
	if err != nil {
		t.Fatalf("ingest failed: %v", err)
	}

	<-done

	if engine.NodeCount() != 3 {
		t.Fatalf("expected 3 nodes after ingest, got %d", engine.NodeCount())
	}
}
