function text(value) {
  if (value === undefined || value === null) return '';
  return String(value).trim();
}

var DIGIT_WORDS = {
  '0': 'zero',
  '1': 'one',
  '2': 'two',
  '3': 'three',
  '4': 'four',
  '5': 'five',
  '6': 'six',
  '7': 'seven',
  '8': 'eight',
  '9': 'nine'
};

function speakDigits(value) {
  var digits = text(value).replace(/\D/g, '');
  if (!digits) return '';
  return digits.split('').map(function (d) {
    return DIGIT_WORDS[d] || d;
  }).join(' ');
}

function stripOrderSuffix(value) {
  return text(value).replace(/_1$/i, '');
}

function speakOrderId(value) {
  var cleaned = stripOrderSuffix(value).toUpperCase().replace(/\s+/g, '');
  var match = cleaned.match(/^SS-?(\d+)$/i);
  var digits = match ? match[1] : cleaned.replace(/\D/g, '');
  if (!digits) return text(value);
  return 'S S dash ' + speakDigits(digits);
}

function displayOrderId(value) {
  var cleaned = stripOrderSuffix(value).toUpperCase().replace(/\s+/g, '');
  var match = cleaned.match(/^SS-?(\d+)$/i);
  if (match) return 'SS-' + match[1];
  var digits = cleaned.replace(/\D/g, '');
  return digits ? 'SS-' + digits : stripOrderSuffix(value);
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
  var payload = payloadOf(found, speak, extra || {});
  return {
    httpStatus: httpStatus,
    bodyText: JSON.stringify(payload),
    found: found,
    speak: speak,
    order_name: payload.order_name,
    action: payload.action
  };
}

function money(amount) {
  var number = Number(amount);
  if (!Number.isFinite(number)) return text(amount);
  var shown = Math.round(number) === number ? String(Math.round(number)) : number.toFixed(2);
  return shown + ' rupees';
}

function parseLineItems(details) {
  var raw = text(details).replace(/\s+/g, ' ');
  if (!raw) return [];
  var chunks = raw.split(/\s*;\s*|\s*\|\s*|\n+/).map(function (part) {
    return part.trim();
  }).filter(Boolean);
  if (chunks.length === 0) chunks = [raw];
  return chunks.map(function (chunk) {
    var qty = '';
    var qtyMatch = chunk.match(/\bQty\s*=\s*([0-9]+(?:\.[0-9]+)?)/i);
    if (qtyMatch) qty = qtyMatch[1];
    var withoutQty = chunk.replace(/\s*Qty\s*=\s*[0-9.]+/gi, '').trim();
    var sku = '';
    var skuMatch = withoutQty.match(/(?:^|\s)-\s*([A-Z]{1,6}\d+)\s*$/i) || withoutQty.match(/\b([A-Z]{1,6}\d+)\s*$/i);
    if (skuMatch) {
      sku = skuMatch[1].toUpperCase();
      withoutQty = withoutQty.replace(/(?:^|\s)-\s*[A-Z]{1,6}\d+\s*$/i, '').replace(/\b[A-Z]{1,6}\d+\s*$/i, '').trim();
    }
    return {
      name: withoutQty || 'Item',
      sku: sku,
      qty: qty
    };
  });
}

function itemsPhrase(details) {
  var items = parseLineItems(details);
  if (items.length === 0) return '';
  return items.map(function (item) {
    var line = item.name;
    if (item.sku) line += ' ' + item.sku;
    if (item.qty) line += ', quantity ' + item.qty;
    return line;
  }).join('. ');
}

function itemLabel(details) {
  var items = parseLineItems(details);
  if (items.length === 0) return '';
  return items[0].name;
}

function speakOrder(order) {
  var status = text(order.status) || 'unknown';
  var line = 'Order ' + speakOrderId(order.order_number);
  if (text(order.shop_name)) line += ' from ' + text(order.shop_name);
  line += ' is ' + status + '.';
  if (text(order.total_price)) line += ' The total is ' + money(order.total_price) + '.';
  var items = itemsPhrase(order.order_details);
  if (items) line += ' ' + items + '.';
  if (text(order.created_at)) line += ' It was placed on ' + text(order.created_at) + '.';
  if (text(order.courier_name)) line += ' The courier is ' + text(order.courier_name) + '.';
  if (text(order.tracking_number)) line += ' The tracking number is ' + speakDigits(order.tracking_number) + '.';
  if (text(order.courier_status) && text(order.courier_status).toLowerCase() !== status.toLowerCase()) {
    line += ' The courier status is ' + text(order.courier_status) + '.';
  }
  return line;
}

function speakMany(orders) {
  var lines = (orders || []).map(function (order) {
    var item = itemLabel(order.order_details) || 'An item';
    return speakOrderId(order.order_number) + ', ' + item + ', is ' + (text(order.status) || 'unknown');
  }).filter(Boolean);
  return 'I found ' + lines.length + ' orders. ' + lines.join('. ') + '. Please say which order id you mean.';
}

function bodyOf(raw) {
  if (raw.body && typeof raw.body === 'object' && !Array.isArray(raw.body)) return raw.body;
  return raw;
}

function readResult(raw, request) {
  var body = bodyOf(raw);
  if (raw.error || (raw.statusCode && Number(raw.statusCode) >= 400) || body.non_field_errors) {
    if (body.non_field_errors) {
      return respond(400, false, 'I need exactly 7 digits of the order number.', request);
    }
    return respond(502, false, 'The order desk could not reach the order service.', request);
  }
  var orders = Array.isArray(body.orders) ? body.orders : [];
  var count = Number(body.count);
  var many = (Number.isFinite(count) && count > 1) || orders.length > 1;
  if (body.success === false || orders.length === 0) {
    return respond(200, false, 'That order is not on the desk.', request);
  }
  if (many) {
    var speak = speakMany(orders);
    return {
      httpStatus: 200,
      bodyText: JSON.stringify({
        found: true,
        speak: speak,
        order_name: '',
        action: request.action || ''
      }),
      found: true,
      speak: speak,
      order_name: '',
      action: request.action || ''
    };
  }
  var order = orders[0];
  return Object.assign(respond(200, true, speakOrder(order), Object.assign({}, request, { order_name: displayOrderId(order.order_number) })), {
    shopify_status: text(order.status)
  });
}

var request = $('Normalize request').first().json;
var result = readResult($input.first().json, request);

if (!result.found || !result.order_name) {
  return [{ json: Object.assign(result, { should_log: false }) }];
}

var prefix = 'Logged a ' + request.request_type + ' request for order ' + speakOrderId(result.order_name) + '. The order was not changed.';
var logged = respond(200, true, prefix, Object.assign({}, request, { order_name: result.order_name }));

return [{
  json: Object.assign(logged, {
    should_log: true,
    sheet_ready: request.sheet_ready,
    created_at: new Date().toISOString(),
    request_type: request.request_type,
    detail: request.detail,
    shopify_status: result.shopify_status
  })
}];
