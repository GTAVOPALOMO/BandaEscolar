import QrScanner from './vendor/qr-scanner.min.js';

const video = document.getElementById('scanner-video');
if (video) {
  const start = document.getElementById('camera-start'), stop = document.getElementById('camera-stop');
  const status = document.getElementById('scanner-status'), code = document.getElementById('id_code');
  const scanner = new QrScanner(video, result => {
    code.value = result.data;
    status.textContent = 'Código leído. Revíselo y confirme el acceso.';
    scanner.stop(); start.hidden = false; stop.hidden = true; code.focus();
  }, {returnDetailedScanResult: true, preferredCamera: 'environment', highlightScanRegion: true, highlightCodeOutline: true});
  start.addEventListener('click', async () => {
    try { await scanner.start(); start.hidden = true; stop.hidden = false; status.textContent = 'Apunte al QR. Después confirme el acceso.'; }
    catch (_) { status.textContent = 'No fue posible abrir la cámara. Revise el permiso o use el código manual.'; }
  });
  stop.addEventListener('click', () => { scanner.stop(); start.hidden = false; stop.hidden = true; });
  window.addEventListener('pagehide', () => scanner.destroy());
}
