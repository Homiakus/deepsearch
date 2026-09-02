package activities

import (
	"context"
	"testing"

	"github.com/Homiakus/SncSinCore/epmemory"
	"github.com/Homiakus/deepsearch/orchestrator/internal/epistemic"
)

func TestEpistemicActivities(t *testing.T) {
	ctx := context.Background()
	corpus := epmemory.Corpus{
		Version: "v1.0",
		Nodes: []epmemory.NodeInput{
			{
				ID:      "claim:hydration",
				Kind:    epmemory.KindProposition,
				Text:    "Hydration is essential for cognitive performance.",
				Context: "general",
				Scope:   "public",
			},
		},
	}

	engine, err := epistemic.NewEngine(epistemic.Config{}, corpus)
	if err != nil {
		t.Fatalf("failed to create engine: %v", err)
	}

	act := NewEpistemicActivities(engine)

	// Ingest new document
	ingestOut, err := act.IngestExtractedDocument(ctx, IngestDocumentInput{
		RunID: "run-1",
		DocID: "doc-1",
		URL:   "https://example.com/hydration",
		Nodes: []epmemory.NodeInput{
			{
				ID:                "evidence:trial-1",
				Kind:              epmemory.KindEvidence,
				Text:              "Clinical trial confirms 2L water daily improves focus.",
				Context:           "general",
				Scope:             "public",
				ProvenanceCluster: "trial-1",
			},
		},
		Edges: []epmemory.EdgeInput{
			{
				From:     "claim:hydration",
				To:       "evidence:trial-1",
				Relation: epmemory.RelEvidenceFor,
			},
		},
	})
	if err != nil {
		t.Fatalf("ingest activity failed: %v", err)
	}

	if ingestOut.TotalNodes != 2 {
		t.Fatalf("expected 2 total nodes, got %d", ingestOut.TotalNodes)
	}

	// Query
	queryOut, err := act.ExecuteEpistemicQuery(ctx, EpistemicQueryInput{
		RunID:        "run-1",
		Text:         "Does water intake help focus?",
		Intent:       "factual",
		Targets:      []string{"claim:hydration"},
		MaxLatencyMS: 1000,
		MaxTokens:    1024,
	})
	if err != nil {
		t.Fatalf("query activity failed: %v", err)
	}

	if queryOut.DigestSHA256 == "" {
		t.Fatal("expected SHA-256 digest in query output")
	}
}
