package server

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/Homiakus/SncSinCore/epmemory"
	"github.com/Homiakus/deepsearch/orchestrator/internal/activities"
	"github.com/Homiakus/deepsearch/orchestrator/internal/epistemic"
)

func TestEpistemicServerEndpoints(t *testing.T) {
	initialCorpus := epmemory.Corpus{
		Version: "v1.0",
		Nodes: []epmemory.NodeInput{
			{
				ID:      "claim:sleep",
				Kind:    epmemory.KindProposition,
				Text:    "Adequate sleep enhances memory consolidation.",
				Context: "neuroscience",
				Scope:   "public",
			},
		},
	}

	engine, err := epistemic.NewEngine(epistemic.Config{}, initialCorpus)
	if err != nil {
		t.Fatalf("failed to create engine: %v", err)
	}

	srv := NewEpistemicServer(engine)

	// 1. Health check
	reqHealth := httptest.NewRequest(http.MethodGet, "/api/v1/epistemic/health", nil)
	recHealth := httptest.NewRecorder()
	srv.ServeHTTP(recHealth, reqHealth)

	if recHealth.Code != http.StatusOK {
		t.Fatalf("expected 200 on health, got %d", recHealth.Code)
	}

	// 2. Ingest
	ingestPayload := activities.IngestDocumentInput{
		RunID: "run-test",
		DocID: "doc-1",
		Nodes: []epmemory.NodeInput{
			{
				ID:                "evidence:rem-study",
				Kind:              epmemory.KindEvidence,
				Text:              "REM sleep duration correlates with memory test score gains.",
				Context:           "neuroscience",
				Scope:             "public",
				ProvenanceCluster: "study-2024",
			},
		},
		Edges: []epmemory.EdgeInput{
			{
				From:     "claim:sleep",
				To:       "evidence:rem-study",
				Relation: epmemory.RelEvidenceFor,
			},
		},
	}
	rawIngest, _ := json.Marshal(ingestPayload)
	reqIngest := httptest.NewRequest(http.MethodPost, "/api/v1/epistemic/ingest", bytes.NewReader(rawIngest))
	recIngest := httptest.NewRecorder()
	srv.ServeHTTP(recIngest, reqIngest)

	if recIngest.Code != http.StatusOK {
		t.Fatalf("expected 200 on ingest, got %d: %s", recIngest.Code, recIngest.Body.String())
	}

	// 3. Query
	queryPayload := activities.EpistemicQueryInput{
		RunID:        "run-test",
		Text:         "How does sleep affect memory?",
		Intent:       "factual",
		Targets:      []string{"claim:sleep"},
		MaxLatencyMS: 1500,
		MaxTokens:    1024,
	}
	rawQuery, _ := json.Marshal(queryPayload)
	reqQuery := httptest.NewRequest(http.MethodPost, "/api/v1/epistemic/query", bytes.NewReader(rawQuery))
	recQuery := httptest.NewRecorder()
	srv.ServeHTTP(recQuery, reqQuery)

	if recQuery.Code != http.StatusOK {
		t.Fatalf("expected 200 on query, got %d: %s", recQuery.Code, recQuery.Body.String())
	}

	var queryResp activities.EpistemicQueryOutput
	if err := json.Unmarshal(recQuery.Body.Bytes(), &queryResp); err != nil {
		t.Fatalf("failed to decode query response: %v", err)
	}

	if queryResp.DigestSHA256 == "" {
		t.Fatal("expected non-empty digest in response")
	}
}
