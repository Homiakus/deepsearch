package epistemic

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"time"

	"github.com/Homiakus/SncSinCore/artifact"
	"github.com/Homiakus/SncSinCore/epaudit"
	"github.com/Homiakus/SncSinCore/epmemory"
	"github.com/Homiakus/SncSinCore/memory"
)

var (
	ErrEngineNotInitialized = errors.New("epistemic engine is not initialized")
	ErrEmptyCorpus          = errors.New("cannot initialize epistemic engine with empty corpus")
	ErrQueryFailed          = errors.New("epistemic query execution failed")
	ErrInvalidArtifact      = errors.New("invalid epistemic artifact generated")
)

// Config holds runtime configuration for the Epistemic Engine.
type Config struct {
	DefaultMaxLatencyMS  int64
	DefaultMaxTokens     int
	StrictContextDefault bool
}

// Engine wraps SncSinCore epmemory and audit services with concurrency safety.
type Engine struct {
	mu      sync.RWMutex
	cfg     Config
	library *epmemory.Library
	corpus  epmemory.Corpus
}

// NewEngine creates a new epistemic engine instance with given config and initial corpus.
func NewEngine(cfg Config, initialCorpus epmemory.Corpus) (*Engine, error) {
	if cfg.DefaultMaxLatencyMS <= 0 {
		cfg.DefaultMaxLatencyMS = 2000
	}
	if cfg.DefaultMaxTokens <= 0 {
		cfg.DefaultMaxTokens = 2048
	}

	lib, err := epmemory.Open(epmemory.Config{}, initialCorpus)
	if err != nil {
		return nil, fmt.Errorf("failed to open epmemory library: %w", err)
	}

	return &Engine{
		cfg:     cfg,
		library: lib,
		corpus:  initialCorpus,
	}, nil
}

// UpdateCorpus atomically updates the underlying knowledge corpus and rebuilds the SIH graph.
func (e *Engine) UpdateCorpus(ctx context.Context, newCorpus epmemory.Corpus) error {
	e.mu.Lock()
	defer e.mu.Unlock()

	lib, err := epmemory.Open(epmemory.Config{}, newCorpus)
	if err != nil {
		return fmt.Errorf("failed to update corpus: %w", err)
	}

	e.library = lib
	e.corpus = newCorpus
	return nil
}

// IngestNodes adds new node and edge inputs to the corpus and updates the engine.
func (e *Engine) IngestNodes(ctx context.Context, nodes []epmemory.NodeInput, edges []epmemory.EdgeInput) error {
	e.mu.Lock()
	defer e.mu.Unlock()

	updatedCorpus := epmemory.Corpus{
		Version: e.corpus.Version,
		Nodes:   append(append([]epmemory.NodeInput(nil), e.corpus.Nodes...), nodes...),
		Edges:   append(append([]epmemory.EdgeInput(nil), e.corpus.Edges...), edges...),
	}

	lib, err := epmemory.Open(epmemory.Config{}, updatedCorpus)
	if err != nil {
		return fmt.Errorf("failed to ingest nodes into corpus: %w", err)
	}

	e.library = lib
	e.corpus = updatedCorpus
	return nil
}

// Query executes an epistemic search query against the SIH graph and returns the verified artifact.
func (e *Engine) Query(ctx context.Context, req epmemory.QueryRequest, budget memory.Budget) (artifact.Artifact, error) {
	e.mu.RLock()
	lib := e.library
	e.mu.RUnlock()

	if lib == nil {
		return artifact.Artifact{}, ErrEngineNotInitialized
	}

	latency := budget.MaxLatency
	if latency <= 0 {
		latency = time.Duration(e.cfg.DefaultMaxLatencyMS) * time.Millisecond
	}
	tokens := budget.MaxContextTokens
	if tokens <= 0 {
		tokens = e.cfg.DefaultMaxTokens
	}

	queryCtx, cancel := context.WithTimeout(ctx, latency)
	defer cancel()

	epBudget := epmemory.Budget{
		MaxLatencyMS:     latency.Milliseconds(),
		MaxContextTokens: tokens,
	}

	out, err := lib.Query(queryCtx, req, epBudget)
	if err != nil {
		return artifact.Artifact{}, fmt.Errorf("%w: %v", ErrQueryFailed, err)
	}

	if err := artifact.Validate(out); err != nil {
		return artifact.Artifact{}, fmt.Errorf("%w: %v", ErrInvalidArtifact, err)
	}

	return out, nil
}

// AuditArtifact performs a deterministic audit of the artifact against an input query and current corpus.
func (e *Engine) AuditArtifact(art artifact.Artifact, req epmemory.QueryRequest) (epaudit.Report, error) {
	e.mu.RLock()
	curCorpus := e.corpus
	e.mu.RUnlock()

	in := epmemory.Input{
		Corpus: curCorpus,
		Query:  req,
	}

	rep := epaudit.Audit(art, in, epaudit.Options{})
	return rep, nil
}

// NodeCount returns the current number of nodes in the corpus.
func (e *Engine) NodeCount() int {
	e.mu.RLock()
	defer e.mu.RUnlock()
	return len(e.corpus.Nodes)
}
