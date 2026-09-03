"use client";

import * as React from "react";
import { FileText, Loader2, CheckCircle2, AlertCircle, Search } from "lucide-react";
import { api } from "@/lib/api-client";
import type { KnowledgeDocument, KnowledgeSearchResult } from "@/lib/api-types";
import { cn, errorMessage } from "@/lib/utils";
import { Dropzone } from "@/components/knowledge/dropzone";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/components/ui/use-toast";

function statusBadge(status: KnowledgeDocument["status"]) {
  switch (status) {
    case "ready":
      return (
        <Badge variant="success">
          <CheckCircle2 className="h-3 w-3" /> Ready
        </Badge>
      );
    case "error":
      return (
        <Badge variant="destructive">
          <AlertCircle className="h-3 w-3" /> Failed
        </Badge>
      );
    default:
      return (
        <Badge variant="secondary">
          <Loader2 className="h-3 w-3 animate-spin" /> Processing
        </Badge>
      );
  }
}

export default function KnowledgePage() {
  const { toast } = useToast();
  const [documents, setDocuments] = React.useState<KnowledgeDocument[]>([]);
  const [isLoadingDocs, setIsLoadingDocs] = React.useState(true);
  const [loadError, setLoadError] = React.useState<string | null>(null);
  const [uploadingCount, setUploadingCount] = React.useState(0);

  const [query, setQuery] = React.useState("");
  const [results, setResults] = React.useState<KnowledgeSearchResult[] | null>(null);
  const [isSearching, setIsSearching] = React.useState(false);
  const [searchError, setSearchError] = React.useState<string | null>(null);

  const loadDocuments = React.useCallback(async () => {
    setIsLoadingDocs(true);
    setLoadError(null);
    try {
      const docs = await api.knowledge.list();
      setDocuments(docs);
    } catch (err) {
      setLoadError(
        errorMessage(err, "Couldn't load your documents right now.")
      );
    } finally {
      setIsLoadingDocs(false);
    }
  }, []);

  React.useEffect(() => {
    loadDocuments();
  }, [loadDocuments]);

  async function handleFiles(files: FileList) {
    const list = Array.from(files);
    setUploadingCount((n) => n + list.length);
    for (const file of list) {
      try {
        // eslint-disable-next-line no-await-in-loop
        const res = await api.knowledge.upload(file);
        setDocuments((prev) => [res.document, ...prev]);
      } catch (err) {
        toast({
          title: `Couldn't upload ${file.name}`,
          description: errorMessage(err, "Please try again."),
          variant: "destructive",
        });
      } finally {
        setUploadingCount((n) => Math.max(0, n - 1));
      }
    }
  }

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;
    setIsSearching(true);
    setSearchError(null);
    try {
      const res = await api.knowledge.search(query.trim());
      setResults(res.results);
    } catch (err) {
      setSearchError(
        errorMessage(err, "Search isn't available right now.")
      );
      setResults(null);
    } finally {
      setIsSearching(false);
    }
  }

  return (
    <div className="mx-auto max-w-4xl px-6 py-8">
      <div className="mb-6">
        <h1 className="font-display text-2xl font-medium text-foreground">Knowledge</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Upload your price lists, FAQs, policies, or service menus. Your agents use these to answer
          customers accurately instead of guessing.
        </p>
      </div>

      <Card className="mb-6">
        <CardHeader>
          <CardTitle className="text-base">Upload documents</CardTitle>
          <CardDescription>PDF and Word documents work best.</CardDescription>
        </CardHeader>
        <CardContent>
          <Dropzone onFiles={handleFiles} disabled={uploadingCount > 0} />
          {uploadingCount > 0 && (
            <p className="mt-3 flex items-center gap-1.5 text-xs text-muted-foreground">
              <Loader2 className="h-3 w-3 animate-spin" /> Uploading {uploadingCount} file
              {uploadingCount > 1 ? "s" : ""}…
            </p>
          )}
        </CardContent>
      </Card>

      <Card className="mb-6">
        <CardHeader>
          <CardTitle className="text-base">Test search</CardTitle>
          <CardDescription>See exactly what your agents would find for a customer question.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSearch} className="flex gap-2">
            <div className="relative flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="e.g. What's your cancellation policy?"
                className="pl-9"
              />
            </div>
            <Button type="submit" disabled={isSearching || !query.trim()}>
              {isSearching ? "Searching…" : "Search"}
            </Button>
          </form>

          {searchError && <p className="mt-3 text-sm text-destructive">{searchError}</p>}

          {results && (
            <div className="mt-4 flex flex-col gap-3">
              {results.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No matches yet — try uploading a document that covers this topic.
                </p>
              ) : (
                results.map((r) => (
                  <div key={r.id} className="rounded-md border border-border bg-secondary/30 p-3">
                    <p className="text-xs font-medium text-muted-foreground">{r.document_filename}</p>
                    <p className="mt-1 text-sm text-foreground">{r.snippet}</p>
                  </div>
                ))
              )}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Your documents</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoadingDocs ? (
            <p className="text-sm text-muted-foreground">Loading documents…</p>
          ) : loadError ? (
            <p className="text-sm text-destructive">{loadError}</p>
          ) : documents.length === 0 ? (
            <div className="rounded-md border border-dashed border-border px-4 py-8 text-center">
              <p className="text-sm text-muted-foreground">
                Nothing uploaded yet. Add a service menu, price list, or FAQ above to get started.
              </p>
            </div>
          ) : (
            <ul className="flex flex-col divide-y divide-border">
              {documents.map((doc) => (
                <li key={doc.id} className="flex items-center justify-between gap-3 py-3">
                  <div className="flex min-w-0 items-center gap-3">
                    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-secondary text-muted-foreground">
                      <FileText className="h-4 w-4" />
                    </span>
                    <span className={cn("truncate text-sm font-medium text-foreground")}>{doc.filename}</span>
                  </div>
                  {statusBadge(doc.status)}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
