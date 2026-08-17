package tests

import (
	"testing"

	"github.com/Homiakus/deepsearch/orchestrator/internal/plan"
)

func TestResearchPlanCompilation(t *testing.T) {
	p, err := plan.CompileResearchPlan()
	if err != nil {
		t.Fatalf("Expected research plan to compile cleanly, got: %v", err)
	}

	if p.ID != "deepsearch-research-v1" {
		t.Errorf("Expected plan ID 'deepsearch-research-v1', got %s", p.ID)
	}

	if len(p.Entry) == 0 {
		t.Errorf("Expected non-empty entry nodes, got %v", p.Entry)
	}

	expectedNodes := []string{
		"NormalizeQuery",
		"PlanResearch",
		"DiscoverSources",
		"RankSeeds",
		"AcquireBatch",
		"ExtractBatch",
		"NormalizeBatch",
		"IndexBatch",
		"BuildEvidence",
		"EvaluateCoverage",
		"BuildArchive",
		"CompleteResearch",
	}

	for _, id := range expectedNodes {
		if _, exists := p.Nodes[id]; !exists {
			t.Errorf("Expected node %q in compiled plan, but was missing", id)
		}
	}
}
