package tests

import (
	"testing"

	"github.com/Homiakus/deepsearch/orchestrator/internal/mapping"
	"github.com/Homiakus/deepsearch/orchestrator/internal/plan"
)

func TestAcquisitionActivityPlanCompilation(t *testing.T) {
	p, err := plan.CompileResearchPlan()
	if err != nil {
		t.Fatalf("Failed to compile research plan: %v", err)
	}

	node, exists := p.Nodes["AcquireBatch"]
	if !exists {
		t.Fatalf("AcquireBatch activity node not found in ResearchPlan")
	}

	if node.Activity != "AcquireBatch" {
		t.Errorf("Expected activity 'AcquireBatch', got '%s'", node.Activity)
	}
	if node.Capability != "crawler" {
		t.Errorf("Expected capability 'crawler', got '%s'", node.Capability)
	}
}

func TestMapAcquireBatchResult(t *testing.T) {
	raw := map[string]interface{}{
		"total_acquired":     float64(10),
		"success_count":      float64(9),
		"failure_count":      float64(1),
		"total_bytes":        float64(102400),
		"total_duration_sec": float64(1.45),
	}

	out, err := mapping.MapAcquireBatchResult(raw)
	if err != nil {
		t.Fatalf("Mapping failed: %v", err)
	}

	if out.TotalAcquired != 10 {
		t.Errorf("Expected TotalAcquired=10, got %d", out.TotalAcquired)
	}
	if out.SuccessCount != 9 {
		t.Errorf("Expected SuccessCount=9, got %d", out.SuccessCount)
	}
	if out.FailureCount != 1 {
		t.Errorf("Expected FailureCount=1, got %d", out.FailureCount)
	}
}
