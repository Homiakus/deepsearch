package mapping

import "time"

type StartRunRequest struct {
	Query            string   `json:"query"`
	Domain           string   `json:"domain,omitempty"`
	PreferredSources []string `json:"preferred_sources,omitempty"`
	Depth            int      `json:"depth,omitempty"`
	MaxPages         int      `json:"max_pages,omitempty"`
	Mode             string   `json:"mode,omitempty"`
	MinMedia         int      `json:"min_media,omitempty"`
	MaxMedia         int      `json:"max_media,omitempty"`
	IdempotencyKey   string   `json:"idempotency_key,omitempty"`
}

type StartRunResponse struct {
	RunID          string    `json:"run_id"`
	IdempotencyKey string    `json:"idempotency_key,omitempty"`
	Status         string    `json:"status"`
	CreatedAt      time.Time `json:"created_at"`
}

type RunStatusResponse struct {
	RunID             string    `json:"run_id"`
	Status            string    `json:"status"`
	Progress          float64   `json:"progress"`
	CurrentNode       string    `json:"current_node,omitempty"`
	PagesProcessed    int       `json:"pages_processed"`
	RagChunksCreated  int       `json:"rag_chunks_created"`
	ErrorMessage      string    `json:"error_message,omitempty"`
	CreatedAt         time.Time `json:"created_at"`
	UpdatedAt         time.Time `json:"updated_at"`
}
