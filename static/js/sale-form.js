const pricesNode = document.getElementById('event-prices');
const eventField = document.getElementById('id_event');
const quantityField = document.getElementById('id_quantity');
const output = document.getElementById('sale-total');
if (pricesNode && eventField && quantityField && output) {
  const prices = JSON.parse(pricesNode.textContent);
  const format = new Intl.NumberFormat('es-CR', {style: 'currency', currency: 'CRC', maximumFractionDigits: 0});
  const update = () => {
    const price = Number(prices[eventField.value] || 0), quantity = Number(quantityField.value || 0);
    output.textContent = price && quantity > 0 ? `Precio unitario: ${format.format(price)} · Total: ${format.format(price * quantity)}` : 'Seleccione evento y cantidad.';
  };
  eventField.addEventListener('change', update); quantityField.addEventListener('input', update); update();
}
