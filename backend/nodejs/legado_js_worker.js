const readline = require('node:readline');
const vm = require('node:vm');
const { createNativeEnv } = require('./legado_shims/native_env');

const rl = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
const pendingBridgeRequests = new Map();
let bridgeSequence = 0;

function sendBridgeHttp(request) {
  const id = `bridge-${++bridgeSequence}`;
  process.stdout.write(JSON.stringify({ type: 'bridge_http', id, request }) + '\n');
  return new Promise((resolve) => {
    pendingBridgeRequests.set(id, resolve);
  });
}

function renderExpressionTemplates(value, sandbox) {
  if (typeof value !== 'string' || !value.includes('{{') || !value.includes('}}')) {
    return value;
  }

  return value.replace(/\{\{(.*?)\}\}/g, (_, expression) => {
    const expr = String(expression || '').trim();
    try {
      const rendered = vm.runInContext(expr, sandbox, { timeout: 1000 });
      return rendered === undefined || rendered === null ? '' : String(rendered);
    } catch (error) {
      return `{{${expr}}}`;
    }
  });
}

rl.on('line', async (line) => {
  const message = JSON.parse(line);

  if (message.type === 'bridge_http_result') {
    const resolver = pendingBridgeRequests.get(message.id);
    if (resolver) {
      pendingBridgeRequests.delete(message.id);
      resolver(message.response || {});
    }
    return;
  }

  if (message.type !== 'execute') {
    return;
  }

  let bridgeHttpCount = 0;
  const env = createNativeEnv(message.context, async (request) => {
    bridgeHttpCount += 1;
    return sendBridgeHttp(request);
  });
  const sandbox = vm.createContext(env);

  try {
    const wrapped = `(async function(){ ${message.code} })()`;
    const rawValue = await vm.runInContext(wrapped, sandbox, { timeout: 5000 });
    const value = renderExpressionTemplates(rawValue, sandbox);
    process.stdout.write(
      JSON.stringify({
        success: true,
        value,
        cache: env.cache._data,
        bridge_http_count: bridgeHttpCount,
      }) + '\n'
    );
  } catch (error) {
    process.stdout.write(
      JSON.stringify({
        success: false,
        error_code: 'JS_RUNTIME_ERROR',
        error: error.message,
        cache: env.cache._data,
        bridge_http_count: bridgeHttpCount,
      }) + '\n'
    );
  }
});
