"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

type Result = {
  columns: string[];
  rows: string[][];
  sql: string;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export default function Home() {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    const trimmed = question.trim();
    if (!trimmed || loading) return;

    setLoading(true);
    setError("");
    setResult(null);
    try {
      const response = await fetch(`${API_URL}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" }, //Tells the server the media type of the data enclosed in the request body
        body: JSON.stringify({ question: trimmed }),
      });
      const data = await response.json();
      if (!response.ok) {
        setError(typeof data.detail === "string" ? data.detail : "The question failed.");
        return;
      }
      setResult(data);
    } catch {
      setError("Could not reach the API. Start it with python -m uvicorn api:app --port 8000.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 px-6 py-16">
      <Card>
        <CardHeader>
          <CardDescription>Gold warehouse</CardDescription>
          <CardTitle className="text-3xl font-semibold tracking-tight">Sales RAG</CardTitle>
          <CardDescription>
            Ask a question. The model writes one SQL query, and the page shows the rows it returns.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="question">Question</Label>
              <Textarea
                id="question"
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                rows={4}
                placeholder="What was the monthly sales revenue in 2021?"
              />
            </div>
            <Button type="submit" disabled={loading || !question.trim()} className="w-fit">
              {loading ? "Asking…" : "Ask"}
            </Button>
          </form>
        </CardContent>
      </Card>

      {error ? (
        <Card>
          <CardContent className="text-sm text-destructive">{error}</CardContent>
        </Card>
      ) : null}

      {result ? (
        <>
          <Card>
            <CardHeader>
              <CardTitle>Rows</CardTitle>
            </CardHeader>
            <CardContent>
              {result.rows.length === 0 ? (
                <p className="text-sm text-muted-foreground">The query returned no rows.</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead>
                      <tr className="border-b">
                        {result.columns.map((column) => (
                          <th key={column} className="px-2 py-2 font-medium">
                            {column}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {result.rows.map((row, index) => (
                        <tr key={index} className="border-b last:border-0">
                          {row.map((cell, cellIndex) => (
                            <td key={cellIndex} className="px-2 py-2">
                              {cell}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>SQL</CardTitle>
            </CardHeader>
            <CardContent>
              <pre className="overflow-x-auto font-mono text-sm leading-6">{result.sql}</pre>
            </CardContent>
          </Card>
        </>
      ) : null}
    </main>
  );
}
