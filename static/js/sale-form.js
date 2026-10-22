const pricesNode = document.getElementById('event-prices');
const eventField = document.getElementById('id_event');
const quantityField = document.getElementById('id_quantity');
const output = document.getElementById('sale-total');
if (pricesNode && eventField && quantityField && output) {
  const prices = JSON.parse(pricesNode.textContent);
  // Match the existing Django crc filter used in receipts and balances.
  const number = new Intl.NumberFormat('es-CR', {maximumFractionDigits: 0});
  const formatCRC = value => '₡' + number.formatToParts(value)
    .map(part => part.type === 'group' ? '.' : part.value).join('');
  const update = () => {
    const price = Number(prices[eventField.value] || 0), quantity = Number(quantityField.value || 0);
    output.textContent = price && quantity > 0 ? `Precio unitario: ${formatCRC(price)} · Total: ${formatCRC(price * quantity)}` : 'Seleccione evento y cantidad.';
  };
  eventField.addEventListener('change', update); quantityField.addEventListener('input', update); update();
}
