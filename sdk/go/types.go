package deepsearch

type HealthResponse struct {
	Status  string `json:"status"`
	App     string `json:"app"`
	Version string `json:"version"`
}

type InspectRequest struct {
	URL string `json:"url"`
}

type InspectResponse struct {
	URL                 string  `json:"url"`
	CanonicalURL        string  `json:"canonical_url"`
	HTTPStatus          int     `json:"http_status"`
	ContentType         string  `json:"content_type"`
	StaticScore         float64 `json:"static_score"`
	JSDependencyScore   float64 `json:"js_dependency_score"`
	DetectedAPIsCount   int     `json:"detected_apis_count"`
	TablesCount         int     `json:"tables_count"`
	CanvasDetected      bool    `json:"canvas_detected"`
	VisualScore         float64 `json:"visual_score"`
	RecommendedStrategy string  `json:"recommended_strategy"`
	EstimatedCost       float64 `json:"estimated_cost"`
}

type CrawlJobRequest struct {
	URL      string `json:"url"`
	MaxDepth int    `json:"max_depth,omitempty"`
	MaxPages int    `json:"max_pages,omitempty"`
	Mode     string `json:"mode,omitempty"`
}

type CrawlJobResponse struct {
	JobID    string `json:"job_id"`
	Status   string `json:"status"`
	URL      string `json:"url"`
	MaxDepth int    `json:"max_depth"`
	MaxPages int    `json:"max_pages"`
}

type SearchQueryRequest struct {
	Query string `json:"query"`
	Limit int    `json:"limit,omitempty"`
}

type SearchResultItem struct {
	URL        string  `json:"url"`
	Title      string  `json:"title"`
	Snippet    string  `json:"snippet"`
	Score      float64 `json:"score"`
	SourceType string  `json:"source_type"`
}

type ResearchRequest struct {
	Query            string   `json:"query"`
	MaxPages         int      `json:"max_pages,omitempty"`
	Depth            int      `json:"depth,omitempty"`
	Mode             string   `json:"mode,omitempty"`
	PreferredSources []string `json:"preferred_sources,omitempty"`
}

type ResearchHandle struct {
	RunID     string  `json:"run_id"`
	Query     string  `json:"query"`
	Status    string  `json:"status"`
	CreatedAt float64 `json:"created_at"`
}

type ResearchStatus struct {
	RunID         string  `json:"run_id"`
	Status        string  `json:"status"`
	PagesCrawled  int     `json:"pages_crawled"`
	EvidenceCount int     `json:"evidence_count"`
	QualityScore  float64 `json:"quality_score"`
}

type ResearchClaim struct {
	ID         string  `json:"id"`
	Text       string  `json:"text"`
	Confidence float64 `json:"confidence"`
	SourceURL  string  `json:"source_url"`
}

type ResearchResult struct {
	RunID           string          `json:"run_id"`
	Query           string          `json:"query"`
	Status          string          `json:"status"`
	Claims          []ResearchClaim `json:"claims"`
	QualityScore    float64         `json:"quality_score"`
	DurationSeconds float64         `json:"duration_seconds"`
}
