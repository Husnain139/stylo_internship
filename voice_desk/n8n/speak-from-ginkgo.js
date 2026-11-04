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

function buildUi(order) {
  return {
    order_number: displayOrderId(order.order_number),
    shop_name: text(order.shop_name),
    status: text(order.status),
    total_price: text(order.total_price),
    created_at: text(order.created_at),
    courier_name: text(order.courier_name),
    tracking_number: text(order.tracking_number),
    products: parseLineItems(order.order_details)
  };
}

function tableMarkdownFromOrders(orderUis) {
  var lines = [
    '| Order | Item | SKU | Qty | Status |',
    '| --- | --- | --- | --- | --- |'
  ];
  var any = false;
  (orderUis || []).forEach(function (orderUi) {
    var products = orderUi.products || [];
    if (products.length === 0) {
      any = true;
      lines.push(
        '| ' + (orderUi.order_number || '—') +
        ' | — | — | — | ' + (orderUi.status || '—') + ' |'
      );
      return;
    }
    products.forEach(function (item) {
      any = true;
      lines.push(
        '| ' + (orderUi.order_number || '—') +
        ' | ' + (item.name || '—') +
        ' | ' + (item.sku || '—') +
        ' | ' + (item.qty || '—') +
        ' | ' + (orderUi.status || '—') + ' |'
      );
    });
  });
  if (!any) lines.push('| — | — | — | — | — |');
  return lines.join('\n');
}

function wrapOrdersUi(orderUis, extra) {
  var ui = Object.assign({
    orders: orderUis
  }, extra || {});
  return {
    ui: ui,
    table_markdown: tableMarkdownFromOrders(orderUis),
    ui_json: JSON.stringify(ui)
  };
}

function speakOrder(order) {
  var status = text(order.status) || 'unknown';
  var orderId = displayOrderId(order.order_number);
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
  line += ' The order id on screen is ' + orderId + '.';
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

function withUi(result, order) {
  if (!order) return result;
  var packed = wrapOrdersUi([buildUi(order)]);
  var payload = {
    found: result.found,
    speak: result.speak,
    order_name: result.order_name || packed.ui.orders[0].order_number,
    action: result.action || '',
    ui: packed.ui,
    table_markdown: packed.table_markdown,
    ui_json: packed.ui_json
  };
  return Object.assign({}, result, {
    bodyText: JSON.stringify(payload),
    ui: packed.ui,
    table_markdown: packed.table_markdown,
    ui_json: packed.ui_json,
    order_name: payload.order_name
  });
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
    var orderUis = (orders || []).map(buildUi).filter(function (orderUi) {
      return orderUi.order_number;
    });
    var choices = orderUis.map(function (orderUi) {
      return {
        order_number: orderUi.order_number,
        item: (orderUi.products[0] && orderUi.products[0].name) || '',
        status: orderUi.status
      };
    });
    var speak = speakMany(orders);
    var packed = wrapOrdersUi(orderUis, { choices: choices });
    var payload = {
      found: true,
      speak: speak,
      order_name: '',
      action: request.action || '',
      choices: choices,
      ui: packed.ui,
      table_markdown: packed.table_markdown,
      ui_json: packed.ui_json
    };
    return {
      httpStatus: 200,
      bodyText: JSON.stringify(payload),
      found: true,
      speak: speak,
      order_name: '',
      action: payload.action,
      choices: choices,
      ui: packed.ui,
      table_markdown: packed.table_markdown,
      ui_json: packed.ui_json
    };
  }
  var order = orders[0];
  var base = Object.assign(respond(200, true, speakOrder(order), Object.assign({}, request, { order_name: displayOrderId(order.order_number) })), {
    shopify_status: text(order.status)
  });
  return withUi(base, order);
}

var request = $('Normalize request').first().json;
return [{ json: readResult($input.first().json, request) }];
