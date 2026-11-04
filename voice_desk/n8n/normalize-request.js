function text(value) {
  if (value === undefined || value === null) return '';
  return String(value).trim();
}

function readConfig(name) {
  try {
    if (typeof $vars !== 'undefined' && $vars[name]) return text($vars[name]);
  } catch (error) {}
  try {
    if (typeof $env !== 'undefined' && $env[name]) return text($env[name]);
  } catch (error) {}
  return '';
}

function payloadOf(found, speak, extra) {
  return {
    found: found,
    speak: speak,
    order_name: extra.order_name || '',
    action: extra.action || ''
  };
}

function respond(httpStatus, found, speak, extra) {
  const payload = payloadOf(found, speak, extra || {});
  return {
    httpStatus: httpStatus,
    bodyText: JSON.stringify(payload),
    found: found,
    speak: speak,
    order_name: payload.order_name,
    action: payload.action
  };
}

function toOrderNumber(value) {
  const raw = text(value).toUpperCase().replace(/\s+/g, '');
  let digits = '';
  const exact = raw.match(/^SS-(\d+)(?:_1)?$/);
  if (exact) digits = exact[1];
  else {
    const underscored = raw.match(/^(\d+)_1$/);
    if (underscored) digits = underscored[1];
    else digits = raw.replace(/\D/g, '');
  }
  if (!/^\d{7}$/.test(digits)) return '';
  return 'SS-' + digits;
}

const root = $input.first().json;
const headers = root.headers || {};
const providedSecret = text(headers['x-desk-secret'] || headers['X-Desk-Secret']);
const expected = readConfig('DESK_SECRET');
const source = root.body && typeof root.body === 'object' && !Array.isArray(root.body) ? root.body : root;
const action = text(source.action);
const requestType = text(source.request_type).toLowerCase();
const detail = text(source.detail);
const base = readConfig('GINKGO_BASE_URL');
const auth = readConfig('GINKGO_AUTH');
const sheetId = readConfig('SHEET_ID');
const orderNumber = toOrderNumber(source.order_number);

if (!expected) {
  return [{ json: respond(500, false, 'The order desk is not configured yet.', { action: action }) }];
}
if (providedSecret !== expected) {
  return [{ json: respond(401, false, 'The order desk refused this request.', { action: action }) }];
}
if (action !== 'lookup_order' && action !== 'log_request') {
  return [{ json: respond(400, false, 'The order desk could not understand that request.', { action: action }) }];
}
if (!orderNumber) {
  return [{ json: respond(400, false, 'I need exactly 7 digits of the order number.', { action: action }) }];
}
if (action === 'log_request' && ['cancel', 'refund', 'exchange', 'other'].indexOf(requestType) === -1) {
  return [{ json: respond(400, false, 'I need a cancel, refund, exchange, or other request.', { action: action }) }];
}
if (!base || !auth) {
  return [{ json: respond(500, false, 'The order desk is not configured yet.', { action: action }) }];
}

const endpoint = base.split('#')[0].split('?')[0];
return [{
  json: {
    httpStatus: 200,
    action: action,
    request_type: requestType,
    detail: detail,
    query_key: 'order_number',
    query_value: orderNumber,
    ginkgo_url: endpoint + '?order_number=' + encodeURIComponent(orderNumber),
    sheet_ready: Boolean(sheetId)
  }
}];
