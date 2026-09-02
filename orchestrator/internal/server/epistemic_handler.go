package server

import (
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"

	"github.com/Homiakus/deepsearch/orchestrator/internal/activities"
	"github.com/Homiakus/deepsearch/orchestrator/internal/epistemic"
)

const maxEpistemicPayloadBytes = 16 * 1024 * 1024 // 16MB

// EpistemicServer handles HTTP/IPC requests for Epistemic Memory operations.
type EpistemicServer struct {
	activities *activities.EpistemicActivities
	engine     *epistemic.Engine
}

// NewEpistemicServer creates a new server instance.
func NewEpistemicServer(engine *epistemic.Engine) *EpistemicServer {
	return &EpistemicServer{
		activities: activities.NewEpistemicActivities(engine),
		engine:     engine,
	}
}

func (s *EpistemicServer) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")

	// Limit request body size to prevent memory exhaustion
	r.Body = http.MaxBytesReader(w, r.Body, maxEpistemicPayloadBytes)

	if r.URL.Path == "/api/v1/epistemic/health" && r.Method == http.MethodGet {
		s.handleHealth(w, r)
		return
	}

	if r.URL.Path == "/api/v1/epistemic/query" && r.Method == http.MethodPost {
		s.handleQuery(w, r)
		return
	}

	if r.URL.Path == "/api/v1/epistemic/ingest" && r.Method == http.MethodPost {
		s.handleIngest(w, r)
		return
	}

	w.WriteHeader(http.StatusNotFound)
	_ = json.NewEncoder(w).Encode(map[string]string{"error": "not found"})
}

func (s *EpistemicServer) handleHealth(w http.ResponseWriter, r *http.Request) {
	nodeCount := 0
	if s.engine != nil {
		nodeCount = s.engine.NodeCount()
	}

	w.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(w).Encode(map[string]any{
		"status":     "ok",
		"service":    "epistemic-daemon",
		"engine":     "SncSinCore-v0.4.0",
		"node_count": nodeCount,
		"timestamp":  time.Now().UTC(),
	})
}

func (s *EpistemicServer) handleQuery(w http.ResponseWriter, r *http.Request) {
	var in activities.EpistemicQueryInput
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		w.WriteHeader(http.StatusBadRequest)
		_ = json.NewEncoder(w).Encode(map[string]string{"error": fmt.Sprintf("invalid query payload: %v", err)})
		return
	}

	if strings.TrimSpace(in.Text) == "" && len(in.Requirements) == 0 {
		w.WriteHeader(http.StatusBadRequest)
		_ = json.NewEncoder(w).Encode(map[string]string{"error": "query text or requirements must be provided"})
		return
	}

	out, err := s.activities.ExecuteEpistemicQuery(r.Context(), in)
	if err != nil {
		w.WriteHeader(http.StatusInternalServerError)
		_ = json.NewEncoder(w).Encode(map[string]string{"error": fmt.Sprintf("epistemic query execution error: %v", err)})
		return
	}

	w.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(w).Encode(out)
}

func (s *EpistemicServer) handleIngest(w http.ResponseWriter, r *http.Request) {
	var in activities.IngestDocumentInput
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		w.WriteHeader(http.StatusBadRequest)
		_ = json.NewEncoder(w).Encode(map[string]string{"error": fmt.Sprintf("invalid ingest payload: %v", err)})
		return
	}

	if len(in.Nodes) == 0 {
		w.WriteHeader(http.StatusBadRequest)
		_ = json.NewEncoder(w).Encode(map[string]string{"error": "at least one node is required for ingestion"})
		return
	}

	out, err := s.activities.IngestExtractedDocument(r.Context(), in)
	if err != nil {
		w.WriteHeader(http.StatusInternalServerError)
		_ = json.NewEncoder(w).Encode(map[string]string{"error": fmt.Sprintf("ingestion error: %v", err)})
		return
	}

	w.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(w).Encode(out)
}
