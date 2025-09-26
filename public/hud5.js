const canvas = document.getElementById("hudCanvas");
const ctx = canvas.getContext("2d");
canvas.width = window.innerWidth;
canvas.height = window.innerHeight;

const ttsAudio = document.getElementById("ttsAudio");
const weatherEl = document.getElementById("weather");
const popup = document.getElementById("popup");

let icon = {
  x: canvas.width - 80,
  y: canvas.height - 80,
  r: 40,
  talking: false,
  angle: 0,
};
let particles = [];
let waveform = [];

// -----------------------------
// Particles & Pulses
// -----------------------------
function spawnParticles() {
  if (icon.talking) {
    for (let i = 0; i < 5; i++) {
      particles.push({
        x: icon.x,
        y: icon.y,
        dx: (Math.random() - 0.5) * 5,
        dy: (Math.random() - 0.5) * 5,
        alpha: 1,
        radius: Math.random() * 3 + 2,
      });
    }
  }
}

function updateParticles() {
  particles.forEach((p) => {
    p.x += p.dx;
    p.y += p.dy;
    p.alpha -= 0.02;
  });
  particles = particles.filter((p) => p.alpha > 0);
}

function drawParticles() {
  particles.forEach((p) => {
    ctx.beginPath();
    ctx.arc(p.x, p.y, p.radius, 0, 2 * Math.PI);
    ctx.fillStyle = `rgba(0,255,255,${p.alpha})`;
    ctx.fill();
  });
}

// -----------------------------
// Waveform
// -----------------------------
function drawWaveform() {
  ctx.beginPath();
  ctx.moveTo(0, canvas.height / 2);
  waveform.forEach((v, i) => {
    ctx.lineTo(i * 2, canvas.height / 2 - v * 50);
  });
  ctx.strokeStyle = "#0ff";
  ctx.lineWidth = 2;
  ctx.shadowBlur = 10;
  ctx.shadowColor = "#0ff";
  ctx.stroke();
}

// -----------------------------
// Draw Icon
// -----------------------------
function drawIcon() {
  ctx.save();
  ctx.translate(icon.x, icon.y);
  let scale = icon.talking
    ? 1 + Math.sin(Date.now() / 100) * 0.3
    : 1 + Math.sin(Date.now() / 200) * 0.1;
  ctx.scale(scale, scale);
  ctx.beginPath();
  ctx.arc(0, 0, icon.r, 0, 2 * Math.PI);
  ctx.fillStyle = "rgba(128,0,255,0.8)";
  ctx.shadowColor = "#fff";
  ctx.shadowBlur = 20;
  ctx.fill();
  ctx.restore();
}

// -----------------------------
// Main Draw Loop
// -----------------------------
function draw() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  drawWaveform();
  drawIcon();
  drawParticles();
  spawnParticles();
  updateParticles();
  requestAnimationFrame(draw);
}

draw();

// -----------------------------
// Update Weather + Time
// -----------------------------
async function updateWeather() {
  try {
    const res = await fetch("/weather");
    const data = await res.json();
    weatherEl.innerHTML = `${data.datetime}<br>${data.weather}`;
  } catch {
    weatherEl.innerHTML = "Weather unavailable";
  }
}

setInterval(updateWeather, 1000);
updateWeather();

// -----------------------------
// Icon Clicks
// -----------------------------
canvas.addEventListener("click", (e) => {
  const dx = e.clientX - icon.x;
  const dy = e.clientY - icon.y;
  if (Math.sqrt(dx * dx + dy * dy) < icon.r) {
    popup.style.display = popup.style.display === "block" ? "none" : "block";
    if (popup.style.display === "block") {
      popup.innerHTML = `<b>Liz AI HUD 5.0</b><br>
      Mood: calm<br>Empathy: 80<br>Curiosity: 60<br>Fun: 50<br>Serious: 70<br>Double-click icon to talk!`;
    }
  }
});

canvas.addEventListener("dblclick", async (e) => {
  const dx = e.clientX - icon.x;
  const dy = e.clientY - icon.y;
  if (Math.sqrt(dx * dx + dy * dy) < icon.r) {
    icon.talking = true;
    try {
      const res = await fetch("/tts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: "สวัสดี! ฉันคือ Liz AI" }),
      });
      const blob = await res.blob();
      ttsAudio.src = URL.createObjectURL(blob);
      ttsAudio.play();
      ttsAudio.onended = () => {
        icon.talking = false;
      };
      // Simulate waveform for TTS
      let t = 0;
      waveform = Array(200)
        .fill(0)
        .map(() => Math.sin((t += 0.3)));
      setTimeout(() => {
        waveform = [];
      }, 4000);
    } catch {
      icon.talking = false;
    }
  }
});
