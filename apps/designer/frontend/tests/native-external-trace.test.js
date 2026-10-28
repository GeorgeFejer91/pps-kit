import assert from "node:assert/strict";
import test from "node:test";
import vm from "node:vm";
import { installNativeExternalLinkTrace } from "./native-external-trace.mjs";

const endpoint = "http://ipc.localhost/designer_open_external";
const destination = "https://doi.org/10.1038/example";
const options = () => ({ method: "POST", body: JSON.stringify({ url: destination }) });
const plain = value => JSON.parse(JSON.stringify(value));

function boundary(fetch, attributes = {}) {
  const window = { location: { href: "http://tauri.localhost/" }, __TAURI_INTERNALS__: {} };
  const invoke = () => { throw new Error("The observer must not invoke or replace IPC"); };
  Object.defineProperty(window.__TAURI_INTERNALS__, "invoke", { value: invoke });
  Object.defineProperty(window, "fetch", { value: fetch, writable: true, configurable: true, enumerable: true, ...attributes });
  const descriptor = Object.getOwnPropertyDescriptor(window, "fetch");
  const context = vm.createContext({ window, URL });
  return {
    window, descriptor, invoke,
    install: () => vm.runInContext(`(${installNativeExternalLinkTrace.toString()})()`, context),
  };
}

test("closure-free observer forwards the real response and restores the exact descriptor without changing immutable invoke", async () => {
  let finish;
  const pending = new Promise(resolve => { finish = resolve; });
  const calls = [];
  const original = function (...args) { calls.push({ receiver: this, args }); return pending; };
  const fixture = boundary(original, { enumerable: false, configurable: false });
  const invokeDescriptor = Object.getOwnPropertyDescriptor(fixture.window.__TAURI_INTERNALS__, "invoke");
  assert.equal(invokeDescriptor.writable, false);
  assert.equal(invokeDescriptor.configurable, false);
  fixture.install();
  const receiver = {};
  const args = [endpoint, options(), "unchanged-extra-argument"];
  const result = fixture.window.fetch.apply(receiver, args);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].receiver, receiver);
  assert.deepEqual(calls[0].args, args);
  assert.deepEqual(plain(fixture.window.externalLinkReceipts), [{ url: destination, method: "POST", pending: true }]);
  const response = new Response("true", { headers: { "Tauri-Response": "ok" } });
  finish(response);
  assert.equal(await result, response);
  assert.equal(response.bodyUsed, false, "observing a clone must not consume Tauri's response");
  assert.equal(await response.json(), true);
  assert.deepEqual(plain(fixture.window.externalLinkReceipts), [{ url: destination, method: "POST", pending: false, reply: "ok", opened: true }]);
  fixture.window.restoreExternalLinkTrace();
  assert.deepEqual(Object.getOwnPropertyDescriptor(fixture.window, "fetch"), fixture.descriptor);
  assert.deepEqual(Object.getOwnPropertyDescriptor(fixture.window.__TAURI_INTERNALS__, "invoke"), invokeDescriptor);
});

test("reply data is recorded verbatim, including false, null and native error payloads", async () => {
  for (const [reply, opened] of [["ok", false], ["ok", null], ["ok", "true"], ["error", "external_browser_unavailable"], ["error", { code: "caller_not_allowed" }]]) {
    const response = new Response(JSON.stringify(opened), { headers: { "Tauri-Response": reply } });
    const fixture = boundary(async () => response);
    fixture.install();
    assert.equal(await fixture.window.fetch(endpoint, options()), response);
    assert.deepEqual(plain(fixture.window.externalLinkReceipts), [{ url: destination, method: "POST", pending: false, reply, opened }]);
    fixture.window.restoreExternalLinkTrace();
  }
});

test("observation failure never rejects or replaces the actual response", async () => {
  for (const fault of ["request-json", "reply-header", "clone", "reply-json"]) {
    const response = {
      headers: { get() { if (fault === "reply-header") throw new Error("header unavailable"); return "ok"; } },
      clone() {
        if (fault === "clone") throw new Error("clone unavailable");
        return { json: async () => { if (fault === "reply-json") throw new Error("bad JSON"); return true; } };
      },
    };
    const fixture = boundary(async () => response);
    fixture.install();
    const request = options();
    if (fault === "request-json") request.body = "not JSON";
    assert.equal(await fixture.window.fetch(endpoint, request), response, fault);
    const [receipt] = fixture.window.externalLinkReceipts;
    assert.equal(receipt.observationFailed, true, fault);
    assert.equal(receipt.pending, false, fault);
    assert.equal(receipt.transportFailed, undefined, fault);
  }
});

test("real fetch rejection is rethrown unchanged and classified as transport failure", async () => {
  for (const synchronous of [false, true]) {
    const failure = new Error("native transport unavailable");
    const fixture = boundary(() => {
      if (synchronous) throw failure;
      return Promise.reject(failure);
    });
    fixture.install();
    await assert.rejects(fixture.window.fetch(endpoint, options()), error => error === failure);
    assert.deepEqual(plain(fixture.window.externalLinkReceipts), [{ url: destination, method: "POST", pending: false, transportFailed: true }]);
    fixture.window.restoreExternalLinkTrace();
    assert.equal(fixture.window.fetch, fixture.descriptor.value);
  }
});

test("only the exact POST command is observed and no request headers or invoke keys are read", async () => {
  const accessed = [];
  let requestHeaderReads = 0;
  const response = {
    headers: { get(name) { accessed.push(name); assert.equal(name, "Tauri-Response"); return "ok"; } },
    clone: () => ({ json: async () => true }),
  };
  const calls = [];
  const fixture = boundary(async (...args) => { calls.push(args); return response; });
  fixture.install();
  const request = options();
  Object.defineProperty(request, "headers", { get() { requestHeaderReads++; throw new Error("invoke keys must never be read"); } });
  assert.equal(await fixture.window.fetch(endpoint, request), response);
  assert.deepEqual(accessed, ["Tauri-Response"]);
  assert.deepEqual(Object.keys(fixture.window.externalLinkReceipts[0]).sort(), ["method", "opened", "pending", "reply", "url"]);
  const otherOptions = { method: "POST", body: "unrelated" };
  Object.defineProperty(otherOptions, "headers", { get() { requestHeaderReads++; throw new Error("other fetch headers must remain untouched"); } });
  for (const address of ["https://doi.org/example", "https://ipc.localhost/designer_open_external", `${endpoint}?other=1`, `${endpoint}/`, "http://ipc.localhost/designer_snapshot"]) {
    assert.equal(await fixture.window.fetch(address, otherOptions), response);
  }
  assert.equal(await fixture.window.fetch(endpoint, { method: "GET" }), response);
  assert.equal(await fixture.window.fetch(endpoint), response);
  assert.equal(calls.length, 8);
  assert.equal(fixture.window.externalLinkReceipts.length, 1);
  assert.equal(requestHeaderReads, 0);
  assert.deepEqual(accessed, ["Tauri-Response"], "other responses are never inspected");
});

test("installation fails promptly for read-only fetch and preserves both descriptors", () => {
  const fixture = boundary(() => {}, { writable: false, configurable: false });
  assert.throws(fixture.install, /requires a writable fetch value/);
  assert.deepEqual(Object.getOwnPropertyDescriptor(fixture.window, "fetch"), fixture.descriptor);
  assert.equal(fixture.window.__TAURI_INTERNALS__.invoke, fixture.invoke);
  assert.equal(fixture.window.externalLinkReceipts, undefined);
});
