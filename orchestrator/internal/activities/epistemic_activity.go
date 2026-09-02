package activities

import (
	"context"
	"fmt"
	"time"

	"github.com/Homiakus/SncSinCore/artifact"
	"github.com/Homiakus/SncSinCore/epmemory"
	"github.com/Homiakus/SncSinCore/memory"
	"github.com/Homiakus/deepsearch/orchestrator/internal/epistemic"
)

// EpistemicQueryInput defines input payload for the ExecuteEpistemicQuery activity.
type EpistemicQueryInput struct {
	RunID         string                      `json:"run_id"`
	Text          string                      `json:"text"`
	Intent        string                      `json:"intent,omitempty"`
	Targets       []string                    `json:"targets,omitempty"`
	Context       string                      `json:"context,omitempty"`
	AllowedScopes []string                    `json:"allowed_scopes,omitempty"`
	StrictContext bool                        `json:"strict_context,omitempty"`
	Requirements  []epmemory.RequirementInput `json:"requirements,omitempty"`
	MaxLatencyMS  int64                       `json:"max_latency_ms,omitempty"`
	MaxTokens     int                         `json:"max_tokens,omitempty"`
}

// EpistemicQueryOutput defines output payload for the ExecuteEpistemicQuery activity.
type EpistemicQueryOutput struct {
	RunID           string            `json:"run_id"`
	Artifact        artifact.Artifact `json:"artifact"`
	Status          string            `json:"status"`
	DigestSHA256    string            `json:"digest_sha256"`
	Coverage        float64           `json:"coverage"`
	ContextPackText string            `json:"context_pack_text,omitempty"`
	ElapsedSec      float64           `json:"elapsed_sec"`
	Timestamp       time.Time         `json:"timestamp"`
}

// IngestDocumentInput defines input payload for compiling and ingesting a document into SIH.
type IngestDocumentInput struct {
	RunID string               `json:"run_id"`
	DocID string               `json:"doc_id"`
	URL   string               `json:"url"`
	Nodes []epmemory.NodeInput `json:"nodes"`
	Edges []epmemory.EdgeInput `json:"edges,omitempty"`
}

// IngestDocumentOutput defines output payload for document ingestion into SIH.
type IngestDocumentOutput struct {
	DocID        string    `json:"doc_id"`
	TotalNodes   int       `json:"total_nodes"`
	IngestedNode int       `json:"ingested_nodes"`
	Timestamp    time.Time `json:"timestamp"`
}

// EpistemicActivities coordinates SncSinCore execution inside the Axiom orchestrator.
type EpistemicActivities struct {
	engine *epistemic.Engine
}

// NewEpistemicActivities creates a new activities receiver with given engine.
func NewEpistemicActivities(engine *epistemic.Engine) *EpistemicActivities {
	return &EpistemicActivities{engine: engine}
}

// ExecuteEpistemicQuery activity executes a bounded query over the epistemic graph.
func (a *EpistemicActivities) ExecuteEpistemicQuery(ctx context.Context, in EpistemicQueryInput) (*EpistemicQueryOutput, error) {
	if a.engine == nil {
		return nil, epistemic.ErrEngineNotInitialized
	}

	start := time.Now()
	intent := epmemory.IntentFactual
	if in.Intent != "" {
		intent = epmemory.Intent(in.Intent)
	}

	req := epmemory.QueryRequest{
		Text:          in.Text,
		Intent:        intent,
		Targets:       in.Targets,
		Context:       in.Context,
		AllowedScopes: in.AllowedScopes,
		StrictContext: in.StrictContext,
		Requirements:  in.Requirements,
	}

	latency := in.MaxLatencyMS
	if latency <= 0 {
		latency = 2000
	}

	art, err := a.engine.Query(ctx, req, memory.Budget{
		MaxLatency:       time.Duration(latency) * time.Millisecond,
		MaxContextTokens: in.MaxTokens,
	})
	if err != nil {
		return nil, fmt.Errorf("epistemic activity failed: %w", err)
	}

	coverage := 0.0
	if len(art.Query.Requirements) > 0 {
		total := 0.0
		for _, r := range art.Query.Requirements {
			total += r.Coverage
		}
		coverage = total / float64(len(art.Query.Requirements))
	}

	return &EpistemicQueryOutput{
		RunID:           in.RunID,
		Artifact:        art,
		Status:          art.Status,
		DigestSHA256:    art.Digest,
		Coverage:        coverage,
		ContextPackText: art.LLM.Text,
		ElapsedSec:      time.Since(start).Seconds(),
		Timestamp:       time.Now().UTC(),
	}, nil
}

// IngestExtractedDocument activity adds new nodes/edges to the SIH memory.
func (a *EpistemicActivities) IngestExtractedDocument(ctx context.Context, in IngestDocumentInput) (*IngestDocumentOutput, error) {
	if a.engine == nil {
		return nil, epistemic.ErrEngineNotInitialized
	}

	if err := a.engine.IngestNodes(ctx, in.Nodes, in.Edges); err != nil {
		return nil, fmt.Errorf("ingest activity failed: %w", err)
	}

	return &IngestDocumentOutput{
		DocID:        in.DocID,
		TotalNodes:   a.engine.NodeCount(),
		IngestedNode: len(in.Nodes),
		Timestamp:    time.Now().UTC(),
	}, nil
}
