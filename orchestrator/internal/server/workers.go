package server

import (
	"fmt"
	"net/http"

	"github.com/Homiakus/axiom/adgo"
)

// NewWorkerServerHandler creates the HTTP handler for the remote worker protocol (§1, §4, DS-A04, DS-A06).
func NewWorkerServerHandler(engine *adgo.Engine, bearerToken string) (http.Handler, error) {
	if engine == nil {
		return nil, fmt.Errorf("adgo engine is required")
	}

	opts := adgo.HTTPWorkerServerOptions{
		BearerToken: bearerToken,
	}
	return adgo.NewHTTPWorkerServer(engine, opts)
}
