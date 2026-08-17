package server

import (
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"

	"github.com/Homiakus/axiom/adgo"
	"github.com/Homiakus/deepsearch/orchestrator/internal/mapping"
)

type APIServer struct {
	engine    *adgo.Engine
	store     adgo.Store
	workerMux http.Handler
}

func NewAPIServer(engine *adgo.Engine, store adgo.Store, workerHandler http.Handler) *APIServer {
	return &APIServer{
		engine:    engine,
		store:     store,
		workerMux: workerHandler,
	}
}

func (s *APIServer) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	// Worker endpoints (/v1/poll, /v1/heartbeat, /v1/complete, /v1/fail)
	if strings.HasPrefix(r.URL.Path, "/v1/") {
		if s.workerMux != nil {
			s.workerMux.ServeHTTP(w, r)
			return
		}
	}

	w.Header().Set("Content-Type", "application/json")

	if r.URL.Path == "/health" && r.Method == http.MethodGet {
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(map[string]any{"status": "ok", "service": "deepsearch-orchestrator", "adgo": "ready"})
		return
	}

	if r.URL.Path == "/api/v1/runs" && r.Method == http.MethodPost {
		s.handleStartRun(w, r)
		return
	}

	if strings.HasPrefix(r.URL.Path, "/api/v1/runs/") {
		runID := strings.TrimPrefix(r.URL.Path, "/api/v1/runs/")
		if strings.HasSuffix(runID, "/cancel") && r.Method == http.MethodPost {
			actualID := strings.TrimSuffix(runID, "/cancel")
			s.handleCancelRun(w, r, actualID)
			return
		}
		if r.Method == http.MethodGet {
			s.handleGetRunStatus(w, r, runID)
			return
		}
	}

	w.WriteHeader(http.StatusNotFound)
	json.NewEncoder(w).Encode(map[string]string{"error": "not found"})
}

func (s *APIServer) handleStartRun(w http.ResponseWriter, r *http.Request) {
	var req mapping.StartRunRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		w.WriteHeader(http.StatusBadRequest)
		json.NewEncoder(w).Encode(map[string]string{"error": fmt.Sprintf("invalid request payload: %v", err)})
		return
	}

	if strings.TrimSpace(req.Query) == "" {
		w.WriteHeader(http.StatusBadRequest)
		json.NewEncoder(w).Encode(map[string]string{"error": "query is required"})
		return
	}

	execID := req.IdempotencyKey
	if execID == "" {
		bytes := make([]byte, 8)
		rand.Read(bytes)
		execID = fmt.Sprintf("ds_adgo_%s", hex.EncodeToString(bytes))
	}

	inputData := map[string]any{
		"query":             req.Query,
		"domain":            req.Domain,
		"preferred_sources": req.PreferredSources,
		"depth":             req.Depth,
		"max_pages":         req.MaxPages,
		"mode":              req.Mode,
		"min_media":         req.MinMedia,
		"max_media":         req.MaxMedia,
	}

	budget := adgo.BudgetLimit{
		MaxCost:           100.0,
		MaxDuration:       15 * time.Minute,
		MaxSearchQueries:  50,
		MaxBrowserFetches: 100,
	}

	exec, err := s.engine.StartOrLoad(r.Context(), execID, inputData, budget)
	if err != nil {
		w.WriteHeader(http.StatusInternalServerError)
		json.NewEncoder(w).Encode(map[string]string{"error": fmt.Sprintf("failed to start run: %v", err)})
		return
	}

	resp := mapping.StartRunResponse{
		RunID:          exec.ID,
		IdempotencyKey: req.IdempotencyKey,
		Status:         string(exec.Status),
		CreatedAt:      exec.CreatedAt,
	}

	w.WriteHeader(http.StatusAccepted)
	json.NewEncoder(w).Encode(resp)
}

func (s *APIServer) handleGetRunStatus(w http.ResponseWriter, r *http.Request, runID string) {
	exec, err := s.engine.Get(r.Context(), runID)
	if err != nil {
		w.WriteHeader(http.StatusNotFound)
		json.NewEncoder(w).Encode(map[string]string{"error": fmt.Sprintf("run %q not found", runID)})
		return
	}

	resp := mapping.RunStatusResponse{
		RunID:        exec.ID,
		Status:       string(exec.Status),
		Progress:     computeProgress(exec),
		CurrentNode:  getCurrentNode(exec),
		CreatedAt:    exec.CreatedAt,
		UpdatedAt:    exec.UpdatedAt,
		ErrorMessage: exec.Failure,
	}

	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(resp)
}

func (s *APIServer) handleCancelRun(w http.ResponseWriter, r *http.Request, runID string) {
	if _, err := s.engine.Cancel(r.Context(), runID, "cancelled via user API"); err != nil {
		w.WriteHeader(http.StatusInternalServerError)
		json.NewEncoder(w).Encode(map[string]string{"error": fmt.Sprintf("failed to cancel run: %v", err)})
		return
	}

	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(map[string]string{"run_id": runID, "status": "canceled"})
}

func computeProgress(exec *adgo.Execution) float64 {
	if exec == nil {
		return 0.0
	}
	if exec.Status == adgo.StatusCompleted {
		return 1.0
	}
	completedNodes := 0
	totalNodes := len(exec.Nodes)
	if totalNodes == 0 {
		return 0.05
	}
	for _, n := range exec.Nodes {
		if n.Status == adgo.NodeCompleted {
			completedNodes++
		}
	}
	return float64(completedNodes) / float64(totalNodes)
}

func getCurrentNode(exec *adgo.Execution) string {
	if exec == nil {
		return ""
	}
	for id, n := range exec.Nodes {
		if n.Status == adgo.NodeRunning || n.Status == adgo.NodePending {
			return id
		}
	}
	return ""
}
