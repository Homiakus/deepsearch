package mapping

import (
	"github.com/Homiakus/deepsearch/orchestrator/internal/activities"
)

// MapAcquireBatchResult converts raw map result from remote worker to typed AcquireBatchOutput.
func MapAcquireBatchResult(data map[string]interface{}) (*activities.AcquireBatchOutput, error) {
	out := &activities.AcquireBatchOutput{}
	if total, ok := data["total_acquired"].(float64); ok {
		out.TotalAcquired = int(total)
	}
	if success, ok := data["success_count"].(float64); ok {
		out.SuccessCount = int(success)
	}
	if failure, ok := data["failure_count"].(float64); ok {
		out.FailureCount = int(failure)
	}
	if bytes, ok := data["total_bytes"].(float64); ok {
		out.TotalBytes = int(bytes)
	}
	if duration, ok := data["total_duration_sec"].(float64); ok {
		out.TotalDurationSec = duration
	}
	return out, nil
}
