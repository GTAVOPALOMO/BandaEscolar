const pricesNode = document.getElementById('event-prices');
const eventField = document.getElementById('id_event');
const quantityField = document.getElementById('id_quantity');
const breakdownField = document.getElementById('id_breakdown');
const rowsNode = document.getElementById('category-rows');
const errorNode = document.getElementById('category-error');
const output = document.getElementById('sale-total');
if (pricesNode && eventField && quantityField && breakdownField && rowsNode && output) {
  const prices = JSON.parse(pricesNode.textContent);
  const money = value => '₡' + new Intl.NumberFormat('es-CR').format(value);
  const update = () => {
    const selected = prices[eventField.value] || [];
    const entries = [...rowsNode.querySelectorAll('input[data-price-id]')].map(input => ({
      price_id: Number(input.dataset.priceId),
      quantity: Number(input.value)
    })).filter(item => Number.isInteger(item.quantity) && item.quantity > 0);
    const count = entries.reduce((sum, item) => sum + item.quantity, 0);
    const total = entries.reduce((sum, item) => {
      const price = selected.find(p => p.id === item.price_id);
      return sum + (price ? price.amount * item.quantity : 0);
    }, 0);
    const quantity = Number(quantityField.value);
    const valid = Number.isInteger(quantity) && quantity > 0 && count === quantity;
    breakdownField.value = JSON.stringify(entries);
    errorNode.textContent = valid ? '' : 'Asigne exactamente ' + (quantity || 0) + ' entradas. Asignadas: ' + count;
    output.textContent = 'Total: ' + money(total);
    const button = document.querySelector('#sale-form button[type="submit"], #sale-form button:not([type])');
    if (button) button.disabled = !valid;
  };
  const render = () => {
    rowsNode.replaceChildren();
    (prices[eventField.value] || []).forEach(price => {
      const label = document.createElement('label');
      label.textContent = price.name + ' (' + money(price.amount) + ') ';
      const input = document.createElement('input');
      input.type = 'number'; input.min = '0'; input.max = '500'; input.step = '1'; input.value = '0';
      input.dataset.priceId = String(price.id);
      input.addEventListener('input', update);
      label.append(input); rowsNode.append(label);
    });
    update();
  };
  eventField.addEventListener('change', render);
  quantityField.addEventListener('input', update);
  render();
}
