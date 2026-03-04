import { useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import Typewriter from "./components/Typewriter.jsx";

const API_BASE_CANDIDATES = [
  import.meta.env.VITE_API_BASE_URL,
  "/api",
  "http://127.0.0.1:8001",
  "http://127.0.0.1:8000",
].filter(Boolean);

async function apiRequest(path, options) {
  let lastError = new Error("Request failed.");
  for (const baseUrl of API_BASE_CANDIDATES) {
    try {
      const resp = await fetch(`${baseUrl}${path}`, options);
      if (!resp.ok) {
        let message = `Request failed (${resp.status})`;
        try {
          const errorBody = await resp.json();
          if (errorBody?.detail) {
            message = String(errorBody.detail);
          }
        } catch (_) {
          // Ignore parse errors and keep status fallback.
        }
        throw new Error(message);
      }
      return await resp.json();
    } catch (err) {
      lastError = err;
    }
  }
  throw lastError;
}

const pageVariants = {
  initial: { opacity: 0, y: 20 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -20 },
};

export default function App() {
  const [step, setStep] = useState("landing");
  const [linkedinUrl, setLinkedinUrl] = useState("");
  const [questions, setQuestions] = useState([]);
  const [answers, setAnswers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [analysis, setAnalysis] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [isReturningUser, setIsReturningUser] = useState(false);
  const [returningFullName, setReturningFullName] = useState("");

  const canAnalyze = linkedinUrl.trim();

  const handleAnalyze = async () => {
    if (!canAnalyze) return;
    setLoading(true);
    setError("");
    try {
      const data = await apiRequest("/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ linkedin_url: linkedinUrl }),
      });

      // ---- Returning user: skip straight to dashboard ----
      if (data.returning_user) {
        setIsReturningUser(true);
        setReturningFullName(data.returning_full_name || "");
        setResult(data.cached_result);
        setStep("dashboard");
        return;
      }

      setIsReturningUser(false);
      setAnalysis(data);
      setQuestions(data.questions || []);
      setAnswers((data.questions || []).map((q) => ({ question: q, answer: "" })));
      setStep("questions");
    } catch (err) {
      setError(err.message || "Could not reach backend API.");
    } finally {
      setLoading(false);
    }
  };

  const handleAnswerChange = (idx, value) => {
    setAnswers((prev) =>
      prev.map((item, i) => (i === idx ? { ...item, answer: value } : item))
    );
  };

  const canSubmit = answers.length > 0 && answers.every((a) => a.answer.trim());

  const handleSubmitAnswers = async () => {
    if (!canSubmit) return;
    setLoading(true);
    setError("");
    try {
      const data = await apiRequest("/submit_answers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          linkedin_url: linkedinUrl,
          answers,
        }),
      });
      setResult(data);
      setStep("dashboard");
    } catch (err) {
      setError(err.message || "Could not reach backend API.");
    } finally {
      setLoading(false);
    }
  };

  const topics = useMemo(() => result?.user_topics || [], [result]);
  const matchedUsers = useMemo(() => result?.matched_users || [], [result]);

  return (
    <div className="min-h-screen px-6 py-10 text-white">
      <div className="mx-auto max-w-6xl">
        <header className="mb-10 flex items-center justify-between">
          <div>
            <h1 className="section-title text-3xl font-semibold">Pro-Tinder</h1>
            <p className="text-slate-400">Professional DNA Matchmaker with GraphRAG</p>
          </div>
          <div className="rounded-full border border-slate-700 px-4 py-2 text-xs uppercase tracking-widest text-slate-300">
            Identity Scanner
          </div>
        </header>

        <AnimatePresence mode="wait">
          {!!error && (
            <motion.div
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              className="mb-6 rounded-xl border border-rose-500/40 bg-rose-500/10 px-4 py-3 text-sm text-rose-200"
            >
              {error}
            </motion.div>
          )}

          {step === "landing" && (
            <motion.section
              key="landing"
              variants={pageVariants}
              initial="initial"
              animate="animate"
              exit="exit"
              className="glass neon-border rounded-3xl p-8"
            >
              <div className="grid gap-8 lg:grid-cols-2">
                <div>
                  <h2 className="section-title text-2xl font-semibold">Scan your professional signature</h2>
                  <p className="mt-2 text-slate-300">
                    Paste a LinkedIn profile URL. We will analyze your profile and find
                    the most similar professionals using AI-powered matching.
                  </p>
                  <div className="mt-6 space-y-4">
                    <input
                      className="w-full rounded-xl border border-slate-700 bg-transparent px-4 py-3 text-sm text-white outline-none focus:border-neon"
                      placeholder="LinkedIn URL"
                      value={linkedinUrl}
                      onChange={(e) => setLinkedinUrl(e.target.value)}
                    />
                    <button
                      onClick={handleAnalyze}
                      disabled={!canAnalyze || loading}
                      className="rounded-xl bg-neon px-5 py-3 text-sm font-semibold text-ink shadow-glow transition hover:opacity-90 disabled:opacity-50"
                    >
                      {loading ? "Analyzing..." : "Run Identity Scan"}
                    </button>
                  </div>
                </div>
                <div className="space-y-4">
                  <div className="glass rounded-2xl p-5">
                    <p className="text-xs uppercase tracking-widest text-slate-400">Signal Layers</p>
                    <ul className="mt-4 space-y-3 text-sm text-slate-200">
                      <li>LinkedIn profile + post analysis</li>
                      <li>GPT-4o mini behavioral Q&A</li>
                      <li>Vector similarity matching</li>
                      <li>Neo4j topic graph enrichment</li>
                      <li>Dynamic LinkedIn search for more matches</li>
                    </ul>
                  </div>
                  <div className="glass rounded-2xl p-5">
                    <p className="text-xs uppercase tracking-widest text-slate-400">Live Output</p>
                    <p className="mt-3 text-sm text-slate-300">
                      Dynamic team assignment with reasoning, interests, and match confidence.
                    </p>
                  </div>
                </div>
              </div>
            </motion.section>
          )}

          {step === "questions" && (
            <motion.section
              key="questions"
              variants={pageVariants}
              initial="initial"
              animate="animate"
              exit="exit"
              className="glass rounded-3xl p-8"
            >
              <div className="mb-6 flex items-center justify-between">
                <div>
                  <h2 className="section-title text-2xl font-semibold">Behavioral Calibration</h2>
                  <p className="text-slate-400">Answer each prompt to refine your team match.</p>
                </div>
                <button
                  onClick={() => setStep("landing")}
                  className="text-xs uppercase tracking-widest text-slate-400"
                >
                  Back
                </button>
              </div>

              <div className="grid gap-6 lg:grid-cols-2">
                <div className="space-y-6">
                  {questions.map((q, idx) => (
                    <div key={q} className="glass rounded-2xl p-5">
                      <Typewriter text={q} />
                      <textarea
                        className="mt-4 h-28 w-full rounded-xl border border-slate-700 bg-transparent px-4 py-3 text-sm text-white outline-none focus:border-neon"
                        placeholder="Your answer..."
                        value={answers[idx]?.answer || ""}
                        onChange={(e) => handleAnswerChange(idx, e.target.value)}
                      />
                    </div>
                  ))}
                </div>
                <div className="space-y-4">
                  <div className="glass rounded-2xl p-5">
                    <p className="text-xs uppercase tracking-widest text-slate-400">AI Context</p>
                    <p className="mt-3 text-sm text-slate-300">
                      {analysis?.reasoning || "Synthesizing your professional narrative."}
                    </p>
                  </div>
                  <div className="glass rounded-2xl p-5">
                    <p className="text-xs uppercase tracking-widest text-slate-400">Recent Posts</p>
                    <ul className="mt-3 space-y-2 text-sm text-slate-300">
                      {(analysis?.recent_posts || []).slice(0, 5).map((post, idx) => (
                        <li key={`${post}-${idx}`} className="line-clamp-3">
                          {post}
                        </li>
                      ))}
                    </ul>
                  </div>
                  <button
                    onClick={handleSubmitAnswers}
                    disabled={!canSubmit || loading}
                    className="w-full rounded-xl bg-neon px-5 py-3 text-sm font-semibold text-ink shadow-glow transition hover:opacity-90 disabled:opacity-50"
                  >
                    {loading ? "Submitting..." : "Submit Answers"}
                  </button>
                </div>
              </div>
            </motion.section>
          )}

          {step === "dashboard" && (
            <motion.section
              key="dashboard"
              variants={pageVariants}
              initial="initial"
              animate="animate"
              exit="exit"
              className="space-y-6"
            >
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="section-title text-2xl font-semibold">Similar Professionals</h2>
                  <p className="text-slate-400">
                    {matchedUsers.length} match{matchedUsers.length !== 1 ? "es" : ""} found
                    {(result?.total_from_db > 0 || result?.total_from_graph > 0 || result?.total_from_linkedin > 0) && " ("}
                    {result?.total_from_db > 0 && `${result.total_from_db} vector`}
                    {result?.total_from_graph > 0 && `${result?.total_from_db > 0 ? ", " : ""}${result.total_from_graph} graph`}
                    {result?.total_from_linkedin > 0 && `${(result?.total_from_db > 0 || result?.total_from_graph > 0) ? ", " : ""}${result.total_from_linkedin} LinkedIn`}
                    {(result?.total_from_db > 0 || result?.total_from_graph > 0 || result?.total_from_linkedin > 0) && ")"}
                  </p>
                </div>
                <button
                  onClick={() => {
                    setStep("landing");
                    setQuestions([]);
                    setAnswers([]);
                    setResult(null);
                    setIsReturningUser(false);
                    setReturningFullName("");
                  }}
                  className="text-xs uppercase tracking-widest text-slate-400 hover:text-white transition"
                >
                  New Scan
                </button>
              </div>

              {/* Welcome back banner */}
              {isReturningUser && (
                <motion.div
                  initial={{ opacity: 0, y: -8 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="flex items-center gap-3 rounded-2xl border border-neon/30 bg-neon/10 px-5 py-4"
                >
                  <span className="text-2xl">👋</span>
                  <div>
                    <p className="text-sm font-semibold text-neon">
                      Welcome back{returningFullName ? `, ${returningFullName}` : ""}!
                    </p>
                    <p className="text-xs text-slate-400">
                      You&apos;ve already been matched. Here are your saved results — no need to go through the scan again.
                    </p>
                  </div>
                </motion.div>
              )}

              {/* User summary row */}
              <div className="grid gap-6 lg:grid-cols-3">
                <div className="glass rounded-2xl p-6 lg:col-span-2">
                  <p className="text-xs uppercase tracking-widest text-slate-400">Your Topics</p>
                  <div className="mt-4 flex flex-wrap gap-2">
                    {topics.map((topic) => (
                      <span
                        key={topic}
                        className="rounded-full border border-neon/40 bg-neon/10 px-3 py-1 text-xs text-neon"
                      >
                        {topic}
                      </span>
                    ))}
                    {!topics.length && (
                      <span className="text-sm text-slate-400">No topics extracted.</span>
                    )}
                  </div>
                </div>
                <div className="glass rounded-2xl p-6">
                  <p className="text-xs uppercase tracking-widest text-slate-400">AI Reasoning</p>
                  <p className="mt-3 text-sm text-slate-300">
                    {result?.user_reasoning || "No reasoning available."}
                  </p>
                </div>
              </div>

              {/* Matched users grid */}
              {matchedUsers.length > 0 ? (
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                  {matchedUsers.map((user, idx) => (
                    <motion.div
                      key={user.linkedin_url || idx}
                      initial={{ opacity: 0, y: 12 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: idx * 0.06 }}
                      className="glass neon-border rounded-2xl p-5 flex flex-col gap-3 hover:border-neon/60 transition"
                    >
                      <div className="flex items-center gap-3">
                        {user.profile_image_url ? (
                          <img
                            src={user.profile_image_url}
                            alt={user.fullName}
                            className="h-12 w-12 rounded-full object-cover border border-slate-600"
                          />
                        ) : (
                          <div className="h-12 w-12 rounded-full bg-slate-700 flex items-center justify-center text-lg font-bold text-slate-300">
                            {(user.fullName || "?")[0]}
                          </div>
                        )}
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-semibold text-white truncate">
                            {user.fullName || "Unknown"}
                          </p>
                          <p className="text-xs text-slate-400 truncate">
                            {user.headline || ""}
                          </p>
                        </div>
                      </div>

                      {user.similarity > 0 && (
                        <div className="flex items-center gap-2">
                          <div className="h-1.5 flex-1 rounded-full bg-slate-700 overflow-hidden">
                            <div
                              className="h-full rounded-full bg-neon"
                              style={{ width: `${Math.round(user.similarity * 100)}%` }}
                            />
                          </div>
                          <span className="text-xs font-mono text-neon">
                            {(user.similarity * 100).toFixed(0)}%
                          </span>
                        </div>
                      )}

                      {user.source === "graph" && (
                        <span className="self-start rounded-full bg-emerald-500/20 border border-emerald-500/40 px-2 py-0.5 text-[10px] uppercase tracking-widest text-emerald-300">
                          Graph
                        </span>
                      )}

                      {user.source === "linkedin_search" && (
                        <span className="self-start rounded-full bg-blue-500/20 border border-blue-500/40 px-2 py-0.5 text-[10px] uppercase tracking-widest text-blue-300">
                          LinkedIn
                        </span>
                      )}

                      <p className="text-xs text-slate-300 line-clamp-3">
                        {user.reason || "Similar professional profile."}
                      </p>

                      {user.topics?.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-auto">
                          {user.topics.slice(0, 3).map((t) => (
                            <span
                              key={t}
                              className="rounded-full border border-slate-700 px-2 py-0.5 text-[10px] text-slate-300"
                            >
                              {t}
                            </span>
                          ))}
                        </div>
                      )}

                      {user.linkedin_url && (
                        <a
                          href={user.linkedin_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="mt-auto text-center rounded-lg border border-slate-600 px-3 py-1.5 text-xs text-slate-300 hover:border-neon hover:text-neon transition"
                        >
                          View Profile
                        </a>
                      )}
                    </motion.div>
                  ))}
                </div>
              ) : (
                <div className="glass rounded-2xl p-10 text-center">
                  <p className="text-slate-400">
                    No similar professionals found yet. As more users join, matches will appear.
                  </p>
                </div>
              )}
            </motion.section>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
