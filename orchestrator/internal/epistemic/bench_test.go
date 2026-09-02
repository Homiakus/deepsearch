package epistemic

import (
	"context"
	"fmt"
	"testing"
	"time"

	"github.com/Homiakus/SncSinCore/epmemory"
	"github.com/Homiakus/SncSinCore/memory"
)

func BenchmarkEpistemicQuery(b *testing.B) {
	ctx := context.Background()
	engine, err := NewEngine(Config{
		DefaultMaxLatencyMS: 2000,
		DefaultMaxTokens:    2048,
	}, sampleCorpus())
	if err != nil {
		b.Fatalf("failed to create engine: %v", err)
	}

	// Ingest propositions with evidence edges
	var nodes []epmemory.NodeInput
	var edges []epmemory.EdgeInput
	for i := 0; i < 20; i++ {
		claimID := fmt.Sprintf("claim:bench:%d", i)
		evID := fmt.Sprintf("evidence:bench:%d", i)
		nodes = append(nodes,
			epmemory.NodeInput{
				ID:                 claimID,
				Kind:               epmemory.KindProposition,
				Text:               fmt.Sprintf("CRDT proposition %d enables deterministic consistency across partitions.", i),
				Belief:             epmemory.Float64(0.95),
				EvidenceQuality:    epmemory.Float64(0.90),
				Context:            "adult-human",
				Scope:              "public",
				ProvenanceCluster: "bench",
			},
			epmemory.NodeInput{
				ID:                 evID,
				Kind:               epmemory.KindEvidence,
				Text:               fmt.Sprintf("Empirical test %d verified partition tolerance.", i),
				Belief:             epmemory.Float64(0.98),
				EvidenceQuality:    epmemory.Float64(0.95),
				Context:            "adult-human",
				Scope:              "public",
				ProvenanceCluster: "bench",
			},
		)
		edges = append(edges, epmemory.EdgeInput{
			From:     claimID,
			To:       evID,
			Relation: epmemory.RelEvidenceFor,
		})
	}
	if err := engine.IngestNodes(ctx, nodes, edges); err != nil {
		b.Fatalf("failed to ingest nodes: %v", err)
	}

	req := epmemory.QueryRequest{
		Text:    "Does caffeine improve alertness?",
		Intent:  epmemory.IntentFactual,
		Targets: []string{"claim:caffeine-alertness"},
		Context: "adult-human",
		Requirements: []epmemory.RequirementInput{
			{
				ID:              "req_1",
				Kind:            epmemory.ReqFact,
				Text:            "Verify consistency",
				Criticality:     epmemory.Float64(1.0),
				MinimumCoverage: epmemory.Float64(0.75),
				Targets:         []string{"claim:caffeine-alertness"},
			},
		},
	}
	budget := memory.Budget{
		MaxLatency:       1 * time.Second,
		MaxContextTokens: 2048,
	}

	b.ResetTimer()
	b.ReportAllocs()

	for i := 0; i < b.N; i++ {
		res, err := engine.Query(ctx, req, budget)
		if err != nil {
			b.Fatalf("query failed: %v", err)
		}
		if res.Digest == "" {
			b.Fatalf("expected non-empty digest")
		}
	}
}

func BenchmarkEpistemicParallelQuery(b *testing.B) {
	ctx := context.Background()
	engine, err := NewEngine(Config{
		DefaultMaxLatencyMS: 2000,
		DefaultMaxTokens:    2048,
	}, sampleCorpus())
	if err != nil {
		b.Fatalf("failed to create engine: %v", err)
	}

	req := epmemory.QueryRequest{
		Text:    "Does caffeine improve alertness?",
		Intent:  epmemory.IntentFactual,
		Targets: []string{"claim:caffeine-alertness"},
		Context: "adult-human",
	}
	budget := memory.Budget{
		MaxLatency:       1 * time.Second,
		MaxContextTokens: 2048,
	}

	b.ResetTimer()
	b.ReportAllocs()

	b.RunParallel(func(pb *testing.PB) {
		for pb.Next() {
			_, err := engine.Query(ctx, req, budget)
			if err != nil {
				b.Errorf("parallel query error: %v", err)
			}
		}
	})
}
