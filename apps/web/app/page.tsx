"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, homeForRole, login } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("teacher@avocado.edu");
  const [password, setPassword] = useState("demo1234");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (typeof window !== "undefined" &&
        new URLSearchParams(window.location.search).get("expired")) {
      setNotice("Your session expired. Please sign in again.");
    }
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(email, password);
      const me = await api.me();
      router.push(homeForRole(me.role));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center p-6">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="mx-auto mb-3 grid place-items-center w-16 h-16 rounded-2xl bg-gradient-to-br from-avocado to-avocado-dark text-3xl shadow-sm">
            🥑
          </div>
          <h1 className="text-3xl font-extrabold text-avocado-dark tracking-tight">
            Avocado
          </h1>
          <p className="text-gray-500 mt-1">
            Instructional intelligence for elementary math
          </p>
        </div>
        <form
          onSubmit={submit}
          className="bg-white rounded-2xl shadow-sm border border-gray-100 p-8 space-y-4"
        >
          <div className="text-center pb-1">
            <div className="font-bold text-gray-800">Welcome back</div>
            <div className="text-xs text-gray-400">
              Sign in to your coaching workspace
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Email
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-avocado"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-avocado"
            />
          </div>
          {notice && (
            <p className="text-sm text-amber-700 bg-amber-50 rounded-lg px-3 py-2">
              {notice}
            </p>
          )}
          {error && <p className="text-sm text-red-600">{error}</p>}
          <button
            disabled={loading}
            className="w-full bg-avocado hover:bg-avocado-dark text-white font-semibold rounded-lg py-2.5 transition disabled:opacity-60"
          >
            {loading ? "Signing in…" : "Sign in"}
          </button>
          <p className="text-xs text-gray-400 text-center pt-2">
            Demo: coach@ · teacher@ · principal@avocado.edu · demo1234
          </p>
        </form>
        <div className="mt-6 flex items-center justify-center gap-4 text-[11px] text-gray-400">
          <span>📊 Data-driven DI</span>
          <span>·</span>
          <span>🎯 Goal tracking</span>
          <span>·</span>
          <span>🤖 AI coaching</span>
        </div>
      </div>
    </main>
  );
}
