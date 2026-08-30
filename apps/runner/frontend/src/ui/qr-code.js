import QRCode from "qrcode";

export async function renderQrCode(canvas, value) {
  if (!canvas) return;
  if (!value) {
    const context = canvas.getContext("2d");
    context?.clearRect(0, 0, canvas.width, canvas.height);
    canvas.hidden = true;
    return;
  }
  canvas.hidden = false;
  await QRCode.toCanvas(canvas, value, {
    errorCorrectionLevel: "M",
    margin: 2,
    width: 212,
    color: { dark: "#202621", light: "#ffffff" },
  });
}
