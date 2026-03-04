"use client";

import { useState, useEffect, useRef } from "react";

const ACCENT = "#F97316";

function useReveal() {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) { el.classList.add("visible"); obs.disconnect(); } },
      { threshold: 0.12 }
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, []);
  return ref;
}

function RevealDiv({ children, className = "", style }: { children: React.ReactNode; className?: string; style?: React.CSSProperties }) {
  const ref = useReveal();
  return <div ref={ref} className={`reveal ${className}`} style={style}>{children}</div>;
}

export default function FlagFoundryPage() {
  const [email, setEmail] = useState("");
  const [submitted, setSubmitted] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (email) setSubmitted(true);
  };

  return (
    <div className="min-h-screen bg-white text-[#0a0a0a]">
      {/* Sticky Nav */}
      <nav className="sticky top-0 z-50 bg-white/90 backdrop-blur border-b border-gray-100">
        <div className="max-w-5xl mx-auto px-6 h-14 flex items-center justify-between">
          <a
            href="https://specialized-model-startups.vercel.app"
            className="text-sm text-gray-500 hover:text-gray-900 transition-colors flex items-center gap-1.5"
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M9 2L4 7l5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            Specialist AI
          </a>
          <span className="font-semibold text-sm tracking-tight">FlagFoundry</span>
          <a
            href="https://github.com/calebnewtonusc/flagfoundry"
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm text-gray-500 hover:text-gray-900 transition-colors flex items-center gap-1.5"
          >
            GitHub
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M5 2h7v7M12 2L2 12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </a>
        </div>
      </nav>

      {/* Hero */}
      <section id="hero" className="max-w-5xl mx-auto px-6 pt-24 pb-20">
        <div className="animate-fade-up delay-0">
          <div
            className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium mb-8 border"
            style={{ borderColor: `${ACCENT}40`, color: ACCENT, backgroundColor: `${ACCENT}08` }}
          >
            <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ backgroundColor: ACCENT }} />
            Training · ETA Q4 2026
          </div>
        </div>

        <h1
          className="serif animate-fade-up delay-1 text-5xl md:text-7xl font-light leading-[1.05] tracking-tight mb-6"
          style={{ animationDelay: "0.1s" }}
        >
          Every flag.
          <br />
          <span style={{ color: ACCENT }}>Every time.</span>
        </h1>

        <p
          className="animate-fade-up text-lg md:text-xl text-gray-500 max-w-2xl leading-relaxed mb-4"
          style={{ animationDelay: "0.2s" }}
        >
          Cybersecurity AI for CTF competitors and security researchers.
        </p>
        <p
          className="animate-fade-up text-base text-gray-400 max-w-2xl leading-relaxed mb-12"
          style={{ animationDelay: "0.25s" }}
        >
          First model trained on the exploit reasoning process — the multi-step chain from &ldquo;I see this binary&rdquo; to &ldquo;here is the working ROP chain&rdquo; — not just vulnerability taxonomy.
        </p>

        {!submitted ? (
          <form
            onSubmit={handleSubmit}
            className="animate-fade-up flex flex-col sm:flex-row gap-3 max-w-md"
            style={{ animationDelay: "0.3s" }}
          >
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="your@email.com"
              required
              className="flex-1 px-4 py-2.5 rounded-lg border border-gray-200 text-sm focus:outline-none focus:border-orange-300 transition-colors bg-white"
            />
            <button
              type="submit"
              className="px-5 py-2.5 rounded-lg text-sm font-medium text-white transition-opacity hover:opacity-90"
              style={{ backgroundColor: ACCENT }}
            >
              Join Waitlist
            </button>
          </form>
        ) : (
          <div
            className="animate-fade-up text-sm font-medium px-4 py-2.5 rounded-lg inline-block"
            style={{ color: ACCENT, backgroundColor: `${ACCENT}10`, border: `1px solid ${ACCENT}30` }}
          >
            You are on the list. We will reach out before launch.
          </div>
        )}
      </section>

      {/* The Gap */}
      <section id="gap" className="border-t border-gray-100 bg-gray-50/50">
        <div className="max-w-5xl mx-auto px-6 py-20">
          <RevealDiv className="mb-12">
            <p className="text-xs font-semibold uppercase tracking-widest text-gray-400 mb-2">The Gap</p>
            <h2 className="serif text-3xl md:text-4xl font-light tracking-tight">
              What changes when a model specializes
            </h2>
          </RevealDiv>
          <div className="grid md:grid-cols-2 gap-6">
            <RevealDiv className="bg-white border border-gray-200 rounded-xl p-6">
              <p className="text-xs font-semibold uppercase tracking-widest text-gray-400 mb-4">General Models</p>
              <p className="text-gray-700 leading-relaxed text-sm">
                Security LLMs describe vulnerability classes. Getting from &ldquo;there&apos;s a UAF here&rdquo; to &ldquo;here&apos;s the 47-step exploit chain for this specific binary&rdquo; requires reasoning no general model can do reliably.
              </p>
              <ul className="mt-4 space-y-2">
                {["Describe vulnerability classes, not exploit chains", "Cannot generate working ROP chains", "Fail on novel challenge compositions", "No reasoning about binary-specific mitigations"].map((item) => (
                  <li key={item} className="flex items-start gap-2 text-sm text-gray-500">
                    <svg className="mt-0.5 shrink-0" width="14" height="14" viewBox="0 0 14 14" fill="none">
                      <circle cx="7" cy="7" r="6" stroke="#E5E7EB" strokeWidth="1.5"/>
                      <path d="M4.5 7l1.5 1.5 3-3" stroke="#9CA3AF" strokeWidth="1.2" strokeLinecap="round"/>
                    </svg>
                    {item}
                  </li>
                ))}
              </ul>
            </RevealDiv>
            <RevealDiv className="border rounded-xl p-6" style={{ borderColor: `${ACCENT}30`, backgroundColor: `${ACCENT}04` }}>
              <p className="text-xs font-semibold uppercase tracking-widest mb-4" style={{ color: ACCENT }}>FlagFoundry</p>
              <p className="text-gray-700 leading-relaxed text-sm">
                FlagFoundry is trained on exploit reasoning chains — the detective process that CTF grandmasters use to go from challenge file to flag submission.
              </p>
              <ul className="mt-4 space-y-2">
                {["Full reasoning chain from challenge to flag", "Working exploit code, not descriptions", "Trained on 50k+ real CTF writeups", "Sandboxed Docker execution for reward signal"].map((item) => (
                  <li key={item} className="flex items-start gap-2 text-sm text-gray-700">
                    <svg className="mt-0.5 shrink-0" width="14" height="14" viewBox="0 0 14 14" fill="none">
                      <circle cx="7" cy="7" r="6" stroke={ACCENT} strokeWidth="1.5" fill={`${ACCENT}15`}/>
                      <path d="M4.5 7l1.5 1.5 3-3" stroke={ACCENT} strokeWidth="1.2" strokeLinecap="round"/>
                    </svg>
                    {item}
                  </li>
                ))}
              </ul>
            </RevealDiv>
          </div>
        </div>
      </section>

      {/* How It's Built */}
      <section id="how" className="max-w-5xl mx-auto px-6 py-20">
        <RevealDiv className="mb-12">
          <p className="text-xs font-semibold uppercase tracking-widest text-gray-400 mb-2">How It&apos;s Built</p>
          <h2 className="serif text-3xl md:text-4xl font-light tracking-tight">
            Three-stage training pipeline
          </h2>
        </RevealDiv>
        <div className="grid md:grid-cols-3 gap-5">
          {[
            {
              stage: "Stage 1",
              name: "Supervised Fine-Tuning",
              desc: "Train on 50k+ writeups from CTFtime, HackTheBox, picoCTF, DEFCON/HITCON — parsed into (challenge → reasoning → exploit → flag) tuples. Model learns the detective process.",
            },
            {
              stage: "Stage 2",
              name: "Reinforcement Learning",
              desc: "Reward signal: binary — flag captured or not — via sandboxed Docker execution. The model learns what reasoning chains actually produce working exploits versus plausible-sounding dead ends.",
            },
            {
              stage: "Stage 3",
              name: "Direct Preference Optimization",
              desc: "DPO on pairs of reasoning chains — successful exploits versus failed attempts on the same challenge. Calibrates the model's reasoning process, not just its final output.",
            },
          ].map((s, i) => (
            <RevealDiv key={s.stage} className="border border-gray-200 rounded-xl p-6 flex flex-col gap-3" style={{ animationDelay: `${i * 0.1}s` }}>
              <div className="flex items-center gap-2">
                <span
                  className="text-xs font-bold px-2 py-0.5 rounded"
                  style={{ color: ACCENT, backgroundColor: `${ACCENT}12` }}
                >
                  {s.stage}
                </span>
              </div>
              <p className="font-semibold text-sm">{s.name}</p>
              <p className="text-sm text-gray-500 leading-relaxed">{s.desc}</p>
            </RevealDiv>
          ))}
        </div>
      </section>

      {/* Capabilities */}
      <section id="capabilities" className="border-t border-gray-100 bg-gray-50/50">
        <div className="max-w-5xl mx-auto px-6 py-20">
          <RevealDiv className="mb-12">
            <p className="text-xs font-semibold uppercase tracking-widest text-gray-400 mb-2">Capabilities</p>
            <h2 className="serif text-3xl md:text-4xl font-light tracking-tight">What it can do</h2>
          </RevealDiv>
          <div className="grid md:grid-cols-2 gap-5">
            {[
              {
                icon: (
                  <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                    <rect x="3" y="5" width="14" height="10" rx="1.5" stroke={ACCENT} strokeWidth="1.5"/>
                    <path d="M7 9l2 2 4-4" stroke={ACCENT} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                ),
                title: "Web Exploitation",
                desc: "SQL injection, XSS, SSRF, deserialization, IDOR — full reasoning chains including payload crafting and filter bypass.",
              },
              {
                icon: (
                  <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                    <path d="M4 6l4 4-4 4M10 14h6" stroke={ACCENT} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                ),
                title: "Binary Exploitation",
                desc: "Buffer overflow, ROP chains, heap exploitation, format strings — generates working shellcode for specific binary configurations.",
              },
              {
                icon: (
                  <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                    <path d="M10 3C6.13 3 3 6.13 3 10s3.13 7 7 7 7-3.13 7-7-3.13-7-7-7z" stroke={ACCENT} strokeWidth="1.5"/>
                    <path d="M10 7v3l2 2" stroke={ACCENT} strokeWidth="1.5" strokeLinecap="round"/>
                  </svg>
                ),
                title: "Cryptography",
                desc: "Weak key recovery, padding oracle attacks, timing attacks — identifies exploitable cryptographic weaknesses from implementation details.",
              },
              {
                icon: (
                  <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                    <path d="M5 15V8l5-4 5 4v7" stroke={ACCENT} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                    <rect x="8" y="11" width="4" height="4" rx="0.5" stroke={ACCENT} strokeWidth="1.5"/>
                  </svg>
                ),
                title: "Forensics & Reverse Engineering",
                desc: "File carving, malware analysis, obfuscation removal — reconstructs logic from compiled binaries and encoded artifacts.",
              },
            ].map((cap) => (
              <RevealDiv key={cap.title} className="bg-white border border-gray-200 rounded-xl p-6 flex gap-4">
                <div className="shrink-0 mt-0.5">{cap.icon}</div>
                <div>
                  <p className="font-semibold text-sm mb-1.5">{cap.title}</p>
                  <p className="text-sm text-gray-500 leading-relaxed">{cap.desc}</p>
                </div>
              </RevealDiv>
            ))}
          </div>
        </div>
      </section>

      {/* Training Stats */}
      <section id="stats" className="max-w-5xl mx-auto px-6 py-20">
        <RevealDiv className="mb-12">
          <p className="text-xs font-semibold uppercase tracking-widest text-gray-400 mb-2">Training</p>
          <h2 className="serif text-3xl md:text-4xl font-light tracking-tight">The numbers behind the model</h2>
        </RevealDiv>
        <div className="grid md:grid-cols-3 gap-5">
          {[
            { label: "Dataset", value: "50k+", sub: "writeups from CTFtime, HackTheBox, picoCTF, DEFCON/HITCON parsed into reasoning tuples" },
            { label: "Base Model", value: "Qwen2.5", sub: "7B-Coder-Instruct — specialized code foundation" },
            { label: "Reward Signal", value: "Binary", sub: "Flag captured or not — via sandboxed Docker execution against live challenge instances" },
          ].map((stat) => (
            <RevealDiv
              key={stat.label}
              className="rounded-xl p-6 border"
              style={{ borderColor: `${ACCENT}25`, backgroundColor: `${ACCENT}05` }}
            >
              <p className="text-xs font-semibold uppercase tracking-widest text-gray-400 mb-2">{stat.label}</p>
              <p className="text-2xl font-bold mb-1" style={{ color: ACCENT }}>{stat.value}</p>
              <p className="text-sm text-gray-500 leading-relaxed">{stat.sub}</p>
            </RevealDiv>
          ))}
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-gray-100">
        <div className="max-w-5xl mx-auto px-6 py-8 flex flex-col sm:flex-row items-center justify-between gap-2">
          <p className="text-xs text-gray-400">
            Part of the{" "}
            <a href="https://specialized-model-startups.vercel.app" className="underline underline-offset-2 hover:text-gray-600 transition-colors">
              Specialist AI
            </a>{" "}
            portfolio
          </p>
          <p className="text-xs text-gray-400">Caleb Newton · USC · 2026</p>
        </div>
      </footer>
    </div>
  );
}
