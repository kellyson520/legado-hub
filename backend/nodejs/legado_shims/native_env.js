const { createJsoup } = require('./jsoup');

function createMapLikeObject(input = {}) {
  const wrapped = { ...input };
  wrapped.get = function get(key) {
    return wrapped[key];
  };
  wrapped.put = function put(key, value) {
    wrapped[key] = value;
    return value;
  };
  wrapped.containsKey = function containsKey(key) {
    return Object.prototype.hasOwnProperty.call(wrapped, key);
  };
  wrapped.getLoginInfoMap = function getLoginInfoMap() {
    return wrapped;
  };
  return wrapped;
}

function coerceResultData(result) {
  if (typeof result === 'string') {
    try {
      return JSON.parse(result);
    } catch (error) {
      return result;
    }
  }
  return result;
}

function resolveSimpleJsonPath(result, path) {
  if (typeof path !== 'string' || !path.startsWith('$.')) {
    return undefined;
  }

  const data = coerceResultData(result);
  if (data === null || typeof data !== 'object') {
    return undefined;
  }

  const parts = path.slice(2).split('.');
  let current = data;
  for (const part of parts) {
    if (current === null || typeof current !== 'object') {
      return undefined;
    }
    current = current[part];
  }
  return current;
}

function normalizeHeaders(headers = {}) {
  const normalized = {};
  for (const [key, value] of Object.entries(headers || {})) {
    normalized[String(key).toLowerCase()] = value;
  }
  return normalized;
}

function createResponseWrapper(response = {}) {
  const text = String(response.text || '');
  const headers = normalizeHeaders(response.headers || {});
  return {
    status: response.status || 0,
    body() {
      return text;
    },
    text() {
      return text;
    },
    html() {
      return text;
    },
    json() {
      return JSON.parse(text);
    },
    header(name) {
      return headers[String(name || '').toLowerCase()] || '';
    },
    headers() {
      return headers;
    },
    match(pattern) {
      return text.match(pattern);
    },
    replace(pattern, replacement) {
      return text.replace(pattern, replacement);
    },
    includes(fragment) {
      return text.includes(fragment);
    },
    split(separator) {
      return text.split(separator);
    },
    trim() {
      return text.trim();
    },
    substring(start, end) {
      return text.substring(start, end);
    },
    indexOf(fragment) {
      return text.indexOf(fragment);
    },
    toString() {
      return text;
    },
    valueOf() {
      return text;
    },
    [Symbol.toPrimitive]() {
      return text;
    },
  };
}

function parseAjaxConfig(config) {
  if (typeof config !== 'string') {
    return config || {};
  }

  const raw = String(config).trim();
  const commaIndex = raw.indexOf(',');
  if (commaIndex > 0) {
    const url = raw.slice(0, commaIndex);
    const optionText = raw.slice(commaIndex + 1).trim();
    if (optionText.startsWith('{')) {
      try {
        const parsed = JSON.parse(optionText);
        return {
          url,
          ...parsed,
        };
      } catch (error) {
        return {
          method: 'GET',
          url: raw,
        };
      }
    }
  }

  return {
    method: 'GET',
    url: raw,
  };
}

function createBridgeJava(sendBridgeHttp, memory, result) {
  return {
    async get(url, headers = {}) {
      if (typeof url === 'string' && !/^https?:\/\//i.test(url) && arguments.length === 1) {
        return memory[url];
      }
      const response = await sendBridgeHttp({ method: 'GET', url, headers, follow_redirects: false });
      return createResponseWrapper(response);
    },
    async post(url, body = '', headers = {}) {
      const response = await sendBridgeHttp({ method: 'POST', url, body, headers, follow_redirects: true });
      return createResponseWrapper(response);
    },
    async ajax(config) {
      const normalized = parseAjaxConfig(config);
      if (normalized.follow_redirects === undefined) {
        normalized.follow_redirects = true;
      }
      const response = await sendBridgeHttp(normalized);
      return createResponseWrapper(response);
    },
    base64Encode(input) {
      return Buffer.from(String(input)).toString('base64');
    },
    base64Decode(input) {
      return Buffer.from(String(input), 'base64').toString('utf8');
    },
    md5Encode(input) {
      return require('node:crypto').createHash('md5').update(String(input)).digest('hex');
    },
    encodeURI(input) {
      return encodeURIComponent(String(input));
    },
    androidId() {
      return 'codex-android-id';
    },
    put(key, value) {
      memory[key] = value;
      return value;
    },
    getString(path) {
      const fromPath = resolveSimpleJsonPath(result, path);
      if (fromPath !== undefined && fromPath !== null) {
        return String(fromPath);
      }
      if (typeof path === 'string' && Object.prototype.hasOwnProperty.call(memory, path)) {
        return String(memory[path]);
      }
      return '';
    },
    log() {
      return null;
    },
    longToast() {
      return null;
    },
  };
}

function createNativeEnv(context, sendBridgeHttp = async () => ({ status: 500, text: 'bridge handler missing' })) {
  const memory = { ...(context.cache || {}) };
  const source = createMapLikeObject(context.source || {});
  const book = createMapLikeObject(context.book || {});
  const variables = { ...(context.variables || {}) };
  source.key = source.key || source.bookSourceUrl || context.baseUrl || '';
  source.getKey = function getKey() {
    return source.key || source.bookSourceUrl || context.baseUrl || '';
  };
  source.getVariable = function getVariable() {
    return source.variable ?? null;
  };
  return {
    result: context.result,
    source,
    book,
    baseUrl: context.baseUrl || '',
    getHost() {
      return context.baseUrl || '';
    },
    urlIP(value) {
      return value;
    },
    cookie: {
      removeCookie() {
        return null;
      },
    },
    variables,
    ...variables,
    cache: {
      _data: memory,
      putMemory(key, value) { this._data[key] = value; },
      getFromMemory(key) { return this._data[key]; },
      put(key, value) { this._data[key] = value; },
      get(key) { return this._data[key]; },
    },
    java: createBridgeJava(sendBridgeHttp, memory, context.result),
    encodeURIComponent,
    org: { jsoup: { Jsoup: createJsoup() } },
    JSON,
    console,
  };
}

module.exports = { createNativeEnv };
