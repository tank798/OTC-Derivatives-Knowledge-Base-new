import assert from "node:assert/strict";
import test from "node:test";

import { RetrievalService } from "../../apps/api/dist/apps/api/src/modules/retrieval/retrieval.service.js";

function createService() {
  const service = new RetrievalService();
  service.core = { QUERY_INSTRUCTION: "query: " };
  return service;
}

function createExtractor(inputs) {
  return async (input) => {
    inputs.push(input);
    return { data: [1, 2, 3] };
  };
}

test("concurrent query embeddings share one extractor initialization", async () => {
  const service = createService();
  const inputs = [];
  let initializeCalls = 0;
  let releaseInitialization;
  const initializationGate = new Promise((resolve) => {
    releaseInitialization = resolve;
  });

  service.initializeExtractor = async () => {
    initializeCalls += 1;
    await initializationGate;
    return createExtractor(inputs);
  };

  const first = service.embedQuery("first");
  const second = service.embedQuery("second");
  await new Promise((resolve) => setImmediate(resolve));

  assert.equal(initializeCalls, 1);
  releaseInitialization();

  const [firstVector, secondVector] = await Promise.all([first, second]);
  assert.deepEqual([...firstVector], [1, 2, 3]);
  assert.deepEqual([...secondVector], [1, 2, 3]);
  assert.deepEqual(inputs.sort(), ["query: first", "query: second"]);

  await service.embedQuery("third");
  assert.equal(initializeCalls, 1);
});

test("failed shared initialization can be retried by a later request", async () => {
  const service = createService();
  const inputs = [];
  let initializeCalls = 0;
  let rejectInitialization;
  const failedInitialization = new Promise((_, reject) => {
    rejectInitialization = reject;
  });

  service.initializeExtractor = async () => {
    initializeCalls += 1;
    if (initializeCalls === 1) return failedInitialization;
    return createExtractor(inputs);
  };

  const first = service.embedQuery("first");
  const second = service.embedQuery("second");
  await new Promise((resolve) => setImmediate(resolve));

  assert.equal(initializeCalls, 1);
  rejectInitialization(new Error("model initialization failed"));

  const failedResults = await Promise.allSettled([first, second]);
  assert.deepEqual(failedResults.map((result) => result.status), ["rejected", "rejected"]);
  assert.match(failedResults[0].reason.message, /model initialization failed/);
  assert.match(failedResults[1].reason.message, /model initialization failed/);

  const retriedVector = await service.embedQuery("retry");
  assert.equal(initializeCalls, 2);
  assert.deepEqual([...retriedVector], [1, 2, 3]);
  assert.deepEqual(inputs, ["query: retry"]);
});
