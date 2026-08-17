package activities

import (
	"time"
)

// ArtifactReference represents a Content Addressable Storage (CAS) reference (DS-RB26).
type ArtifactReference struct {
	ContentHash  string `json:"content_hash"`
	URI          string `json:"uri"`
	MediaType    string `json:"media_type"`
	SizeBytes    int    `json:"size_bytes"`
	MetadataHash string `json:"metadata_hash,omitempty"`
}

// QualityReport represents page quality evaluation signals (DS-RB05).
type QualityReport struct {
	Score               float64  `json:"score"`
	Completeness        float64  `json:"completeness"`
	Blocked             bool     `json:"blocked"`
	LikelyUnrendered    bool     `json:"likely_unrendered"`
	Reasons             []string `json:"reasons,omitempty"`
	SuggestedEscalation string   `json:"suggested_escalation,omitempty"`
}

// CostReport represents resource consumption metrics for acquisition (DS-RB32).
type CostReport struct {
	BaseCost        float64 `json:"base_cost"`
	ExecutionTimeMs float64 `json:"execution_time_ms"`
	MemoryMB        float64 `json:"memory_mb"`
	NetworkBytes    int     `json:"network_bytes"`
	CPUTimeMs       float64 `json:"cpu_time_ms"`
}

// FailureRecord represents typed acquisition failure details (DS-RB31).
type FailureRecord struct {
	FailureClass      string  `json:"failure_class"`
	Message           string  `json:"message"`
	Retryable         bool    `json:"retryable"`
	RetryAfterSeconds float64 `json:"retry_after_seconds,omitempty"`
	Timestamp         float64 `json:"timestamp"`
}

// AcquisitionResult represents a standardized acquisition outcome.
type AcquisitionResult struct {
	RequestedURL     string              `json:"requested_url"`
	FinalURL         string              `json:"final_url"`
	Backend          string              `json:"backend"`
	BackendVersion   string              `json:"backend_version"`
	StatusCode       int                 `json:"status_code"`
	Headers          map[string]string   `json:"headers,omitempty"`
	ContentType      string              `json:"content_type"`
	TextPreview      string              `json:"text_preview,omitempty"`
	ArtifactRefs     []ArtifactReference `json:"artifact_refs,omitempty"`
	Quality          QualityReport       `json:"quality"`
	Cost             CostReport          `json:"cost"`
	Failure          *FailureRecord      `json:"failure,omitempty"`
	ElapsedSec       float64             `json:"elapsed_sec"`
	CapabilitiesUsed []string            `json:"capabilities_used,omitempty"`
}

// AcquireBatchInput represents input payload for AcquireBatch activity (DS-RB28).
type AcquireBatchInput struct {
	RunID          string   `json:"run_id"`
	BatchID        string   `json:"batch_id"`
	URLs           []string `json:"urls"`
	Mode           string   `json:"mode,omitempty"`
	CASStorageDir  string   `json:"cas_storage_dir,omitempty"`
	TimeoutSeconds int      `json:"timeout_seconds,omitempty"`
}

// AcquireBatchOutput represents output payload for AcquireBatch activity (DS-RB28).
type AcquireBatchOutput struct {
	Results          []AcquisitionResult `json:"results"`
	TotalAcquired    int                 `json:"total_acquired"`
	SuccessCount     int                 `json:"success_count"`
	FailureCount     int                 `json:"failure_count"`
	TotalBytes       int                 `json:"total_bytes"`
	TotalDurationSec float64             `json:"total_duration_sec"`
	Timestamp        time.Time           `json:"timestamp"`
}
