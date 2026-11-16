package main

import (
	"go/ast"
	"go/parser"
	"go/token"
	"net/http"
	"path/filepath"
	"reflect"
	"runtime"
	"testing"
	"time"

	"github.com/evcc-io/evcc/util/request"
)

// Inspect the actual patched dependency selected by build.py, without creating an
// account, reading credentials, or invoking a provider constructor.
func TestMazdaAuthUsesGateWithoutBodyLogging(t *testing.T) {
	function := runtime.FuncForPC(reflect.ValueOf(request.NewClient).Pointer())
	requestFile, _ := function.FileLine(function.Entry())
	upstream := filepath.Dir(filepath.Dir(filepath.Dir(requestFile)))
	source, err := parser.ParseFile(token.NewFileSet(), filepath.Join(upstream, "vehicle", "mazda_identity.go"), nil, 0)
	if err != nil {
		t.Fatalf("read effective patched Mazda source: %v", err)
	}
	clients := 0
	ast.Inspect(source, func(node ast.Node) bool {
		assignment, ok := node.(*ast.AssignStmt)
		if !ok || len(assignment.Lhs) != 1 || len(assignment.Rhs) != 1 {
			return true
		}
		name, ok := assignment.Lhs[0].(*ast.Ident)
		if !ok || name.Name != "authHTTP" {
			return true
		}
		clients++
		address, ok := assignment.Rhs[0].(*ast.UnaryExpr)
		if !ok || address.Op != token.AND {
			t.Fatal("Mazda authentication client construction changed")
		}
		client, ok := address.X.(*ast.CompositeLit)
		if !ok {
			t.Fatal("Mazda authentication client is not a literal")
		}
		for _, element := range client.Elts {
			field, ok := element.(*ast.KeyValueExpr)
			if !ok {
				continue
			}
			key, ok := field.Key.(*ast.Ident)
			if !ok || key.Name != "Transport" {
				continue
			}
			call, ok := field.Value.(*ast.CallExpr)
			if !ok || len(call.Args) != 1 || !packageFunction(call.Fun, "request", "DBusEVTransport") {
				t.Fatal("Mazda authentication must use the shared gate directly, without NewTripper body logging")
			}
			base, ok := call.Args[0].(*ast.CallExpr)
			if !ok || len(base.Args) != 0 || !packageFunction(base.Fun, "transport", "Default") {
				t.Fatal("Mazda authentication must preserve the reviewed TLS transport")
			}
			return false
		}
		t.Fatal("Mazda authentication has no explicitly gated transport")
		return false
	})
	if clients != 1 {
		t.Fatalf("expected one Mazda authentication client, found %d", clients)
	}
}

func packageFunction(expression ast.Expr, pkg, name string) bool {
	selector, ok := expression.(*ast.SelectorExpr)
	if !ok || selector.Sel.Name != name {
		return false
	}
	owner, ok := selector.X.(*ast.Ident)
	return ok && owner.Name == pkg
}

func TestMazdaAuthGateBlocksPausedRequestBeforeTransport(t *testing.T) {
	now := time.Now()
	gate, err := newTraffic(filepath.Join(t.TempDir(), "traffic.json"))
	if err != nil {
		t.Fatal(err)
	}
	gate.now = func() time.Time { return now }
	gate.state.Pause = now.Add(time.Hour)
	gate.state.Reason = "auth"
	previous := request.DBusEVTransport
	request.DBusEVTransport = gate.wrap
	t.Cleanup(func() { request.DBusEVTransport = previous })
	base := &fakeTransport{status: http.StatusOK, now: &now}
	client := &http.Client{Timeout: request.Timeout, Transport: request.DBusEVTransport(base)}
	req, _ := http.NewRequest(http.MethodPost, "https://example.invalid/auth", http.NoBody)
	if _, err := client.Do(req); err == nil {
		t.Fatal("paused Mazda authentication was admitted")
	}
	if base.calls != 0 || gate.state.Count != 0 {
		t.Fatal("paused authentication reached the underlying transport")
	}
}
