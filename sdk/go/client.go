package deepsearch

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

type Client struct {
	BaseURL    string
	APIKey     string
	HTTPClient *http.Client
}

func NewClient(baseURL, apiKey string) *Client {
	if baseURL == "" {
		baseURL = "http://localhost:8080/api/v1"
	}
	baseURL = strings.TrimRight(baseURL, "/")
	return &Client{
		BaseURL: baseURL,
		APIKey:  apiKey,
		HTTPClient: &http.Client{
			Timeout: 30 * time.Second,
		},
	}
}

func (c *Client) doRequest(ctx context.Context, method, path string, body interface{}, out interface{}) error {
	var bodyReader io.Reader
	if body != nil {
		data, err := json.Marshal(body)
		if err != nil {
			return err
		}
		bodyReader = bytes.NewReader(data)
	}

	req, err := http.NewRequestWithContext(ctx, method, c.BaseURL+path, bodyReader)
	if err != nil {
		return err
	}

	req.Header.Set("Content-Type", "application/json")
	if c.APIKey != "" {
		req.Header.Set("Authorization", "Bearer "+c.APIKey)
	}

	resp, err := c.HTTPClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		respBody, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("deepsearch api error [%d]: %s", resp.StatusCode, string(respBody))
	}

	if out != nil {
		return json.NewDecoder(resp.Body).Decode(out)
	}
	return nil
}

func (c *Client) GetHealth(ctx context.Context) (*HealthResponse, error) {
	var res HealthResponse
	err := c.doRequest(ctx, http.MethodGet, "/health", nil, &res)
	return &res, err
}

func (c *Client) InspectURL(ctx context.Context, url string) (*InspectResponse, error) {
	var res InspectResponse
	err := c.doRequest(ctx, http.MethodPost, "/inspect", &InspectRequest{URL: url}, &res)
	return &res, err
}

func (c *Client) StartCrawl(ctx context.Context, req *CrawlJobRequest) (*CrawlJobResponse, error) {
	var res CrawlJobResponse
	err := c.doRequest(ctx, http.MethodPost, "/crawl", req, &res)
	return &res, err
}

func (c *Client) SearchHybrid(ctx context.Context, query string, limit int) ([]SearchResultItem, error) {
	var res []SearchResultItem
	err := c.doRequest(ctx, http.MethodPost, "/search/hybrid", &SearchQueryRequest{Query: query, Limit: limit}, &res)
	return res, err
}

func (c *Client) StartResearch(ctx context.Context, req *ResearchRequest) (*ResearchHandle, error) {
	var res ResearchHandle
	err := c.doRequest(ctx, http.MethodPost, "/research", req, &res)
	return &res, err
}

func (c *Client) GetResearchStatus(ctx context.Context, runID string) (*ResearchStatus, error) {
	var res ResearchStatus
	err := c.doRequest(ctx, http.MethodGet, "/research/"+runID, nil, &res)
	return &res, err
}

func (c *Client) GetResearchResult(ctx context.Context, runID string) (*ResearchResult, error) {
	var res ResearchResult
	err := c.doRequest(ctx, http.MethodGet, "/research/"+runID+"/result", nil, &res)
	return &res, err
}

func (c *Client) CancelResearch(ctx context.Context, runID string) error {
	return c.doRequest(ctx, http.MethodPost, "/research/"+runID+"/cancel", nil, nil)
}
