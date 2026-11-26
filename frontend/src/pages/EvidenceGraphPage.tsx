import * as React from "react";
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
  useEdgesState,
  useNodesState,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { AlertTriangle, FileText, GitBranch, Network, Search, ShieldAlert, Users, X } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { NoAnalysisEmptyState, PageHeader } from "@/components/ui/PageHeader";
import { useAnalysis } from "@/context/AnalysisContext";
import { extractApiError, fetchGraph } from "@/lib/api";
import type { GraphResponse } from "@/types/cerberus";

function DocumentNode({ data, selected }: NodeProps) {
  const suspicious = Boolean(data.is_suspicious);
  return (
    <div
      className={`min-w-[200px] max-w-[240px] rounded-xl border px-3.5 py-2.5 shadow-lg transition ${
        suspicious
          ? "border-rose-500/70 bg-[#230f1e]"
          : selected
          ? "border-cyan-400 bg-[#0f2452]"
          : "border-blue-500/40 bg-[#0b193b]"
      }`}
    >
      <Handle type="source" position={Position.Right} className="!bg-cyan-400" />
      <div className="flex items-center justify-between gap-2 text-[10px] font-semibold uppercase tracking-wider text-cyan-300">
        <span className="flex items-center gap-1">
          <FileText className="h-3 w-3" /> Document
        </span>
        {suspicious && <ShieldAlert className="h-3.5 w-3.5 text-rose-400" />}
      </div>
      <div className="mt-1 truncate text-xs font-semibold text-white">
        {String(data.filename ?? data.label ?? "")}
      </div>
      <div className="mt-1 text-[10px] text-slate-400">
        {String(data.file_type ?? "").toUpperCase()} · rel{" "}
        {Math.round(Number(data.reliability ?? 0) * 100)}%
      </div>
    </div>
  );
}

function ClaimNode({ data, selected }: NodeProps) {
  const status = String(data.status ?? "unverified");
  const suspicious = Boolean(data.suspicious);
  const borderColor = suspicious
    ? "border-rose-500/80 bg-[#261121]"
    : status === "disputed"
    ? "border-amber-400/70 bg-[#261c0e]"
    : status === "verified"
    ? "border-emerald-400/50 bg-[#0a2324]"
    : "border-purple-400/40 bg-[#141738]";

  return (
    <div
      className={`min-w-[210px] max-w-[250px] rounded-xl border px-3.5 py-2.5 shadow-lg ${borderColor} ${
        selected ? "ring-2 ring-cyan-400" : ""
      }`}
    >
      <Handle type="target" position={Position.Left} className="!bg-blue-400" />
      <Handle type="source" position={Position.Right} className="!bg-purple-400" />
      <div className="flex items-center justify-between gap-2 text-[10px] font-semibold uppercase tracking-wider text-purple-300">
        <span>Claim</span>
        <span className="rounded bg-black/30 px-1.5 py-0.5 text-[9px] text-slate-200">
          {status}
        </span>
      </div>
      <div className="mt-1 truncate text-xs font-semibold text-white">
        {String(data.label ?? "")}
      </div>
      <div className="mt-1 truncate text-[10px] text-slate-400">
        {String(data.entity_name ?? "")} {data.locator ? `· ${String(data.locator)}` : ""}
      </div>
    </div>
  );
}

function EntityNode({ data, selected }: NodeProps) {
  const aliases = Array.isArray(data.aliases) ? data.aliases : [];
  return (
    <div
      className={`min-w-[190px] max-w-[240px] rounded-xl border px-3.5 py-2.5 shadow-lg ${
        selected
          ? "border-cyan-400 bg-[#0e2a4a]"
          : "border-cyan-500/40 bg-[#091f38]"
      }`}
    >
      <Handle type="target" position={Position.Left} className="!bg-cyan-400" />
      <div className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-cyan-300">
        <Users className="h-3 w-3" /> Entity ({String(data.entity_type ?? "unknown")})
      </div>
      <div className="mt-1 truncate text-xs font-semibold text-white">
        {String(data.label ?? "")}
      </div>
      {aliases.length > 0 && (
        <div className="mt-1 truncate text-[10px] text-slate-400">
          Aliases: {aliases.join(", ")}
        </div>
      )}
    </div>
  );
}

function ConflictNode({ data, selected }: NodeProps) {
  return (
    <div
      className={`min-w-[200px] max-w-[240px] rounded-xl border border-rose-500/70 bg-[#2b0f1d] px-3.5 py-2.5 shadow-lg ${
        selected ? "ring-2 ring-cyan-400" : ""
      }`}
    >
      <Handle type="target" position={Position.Left} className="!bg-rose-400" />
      <div className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-rose-300">
        <AlertTriangle className="h-3 w-3" /> Conflict ({String(data.severity ?? "medium")})
      </div>
      <div className="mt-1 truncate text-xs font-semibold text-white">
        {String(data.label ?? "")}
      </div>
      <div className="mt-1 truncate text-[10px] text-rose-200/80">
        {String(data.entity_name ?? "")}
      </div>
    </div>
  );
}

const NODE_TYPES = {
  document: DocumentNode,
  claim: ClaimNode,
  entity: EntityNode,
  conflict: ConflictNode,
};

function edgeColor(relation: string): string {
  if (relation === "CONTRADICTS" || relation === "CONFLICT_LINK") return "#f43f5e";
  if (relation === "STAGE_DIFFERENCE") return "#22d3ee";
  if (relation === "SUPERSEDES") return "#a855f7";
  if (relation === "COMPATIBLE_WITH") return "#10b981";
  if (relation === "ABOUT") return "#38bdf8";
  return "#64748b";
}

export function EvidenceGraphPage() {
  const { activeAnalysisId, activeAnalysis } = useAnalysis();
  const [graphData, setGraphData] = React.useState<GraphResponse | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const [search, setSearch] = React.useState("");
  const [visibleTypes, setVisibleTypes] = React.useState<Record<string, boolean>>({
    document: true,
    claim: true,
    entity: true,
    conflict: true,
  });
  const [selectedItem, setSelectedItem] = React.useState<{
    kind: "node" | "edge";
    title: string;
    data: Record<string, unknown>;
  } | null>(null);

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

  React.useEffect(() => {
    if (!activeAnalysisId) {
      setGraphData(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchGraph(activeAnalysisId)
      .then((res) => {
        if (!cancelled) setGraphData(res);
      })
      .catch((err) => {
        if (!cancelled) setError(extractApiError(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeAnalysisId]);

  React.useEffect(() => {
    if (!graphData) {
      setNodes([]);
      setEdges([]);
      return;
    }

    const q = search.trim().toLowerCase();
    const rawNodes: Node[] = graphData.nodes.map((n) => ({
      id: n.id,
      type: n.type in NODE_TYPES ? n.type : "claim",
      position: n.position,
      data: n.data,
    }));

    const rawEdges: Edge[] = graphData.edges.map((e) => {
      const relation = String(e.data.relation ?? e.label ?? "");
      const color = edgeColor(relation);
      return {
        id: e.id,
        source: e.source,
        target: e.target,
        label: e.label,
        type: "smoothstep",
        animated: e.animated,
        style: { stroke: color, strokeWidth: relation === "CONTRADICTS" ? 2.4 : 1.5 },
        labelStyle: { fill: "#cbd5e1", fontSize: 10, fontWeight: 600 },
        labelBgStyle: { fill: "#071026", fillOpacity: 0.85 },
        markerEnd: { type: MarkerType.ArrowClosed, color },
        data: e.data,
      };
    });

    // Add real conflict nodes from activeAnalysis.conflicts when enabled
    if (visibleTypes.conflict && activeAnalysis?.conflicts?.length) {
      activeAnalysis.conflicts.forEach((cf, idx) => {
        const nodeId = `conflict_node_${cf.id}`;
        rawNodes.push({
          id: nodeId,
          type: "conflict",
          position: { x: 1180, y: 40 + idx * 145 },
          data: {
            label: cf.conflict_type.replace(/_/g, " "),
            entity_name: cf.entity_name,
            predicate: cf.predicate,
            severity: cf.severity,
            explanation: cf.explanation,
            rule: cf.rule,
            is_real_problem: cf.is_real_problem,
            nodeType: "conflict",
          },
        });
        cf.claim_ids.forEach((cid) => {
          rawEdges.push({
            id: `cfl_edge_${cf.id}_${cid}`,
            source: cid,
            target: nodeId,
            label: cf.is_real_problem ? "CONTRADICTION" : cf.conflict_type,
            type: "smoothstep",
            animated: cf.is_real_problem,
            style: {
              stroke: cf.is_real_problem ? "#f43f5e" : "#f59e0b",
              strokeWidth: 1.6,
              strokeDasharray: cf.is_real_problem ? undefined : "5 4",
            },
            labelStyle: { fill: "#fda4af", fontSize: 9 },
            labelBgStyle: { fill: "#071026", fillOpacity: 0.85 },
            data: { relation: "CONFLICT_LINK", explanation: cf.explanation, rule: cf.rule },
          });
        });
      });
    }

    const filteredNodes = rawNodes.filter((n) => {
      const ntype = String(n.type ?? "claim");
      if (!visibleTypes[ntype]) return false;
      if (!q) return true;
      const blob = JSON.stringify(n.data).toLowerCase();
      return blob.includes(q) || n.id.toLowerCase().includes(q);
    });
    const visibleIds = new Set(filteredNodes.map((n) => n.id));
    const filteredEdges = rawEdges.filter(
      (e) => visibleIds.has(e.source) && visibleIds.has(e.target)
    );

    setNodes(filteredNodes);
    setEdges(filteredEdges);
  }, [activeAnalysis, graphData, search, setEdges, setNodes, visibleTypes]);

  return (
    <div className="animate-fade-in space-y-5">
      <PageHeader
        eyebrow="Knowledge Graph Engine"
        title="Evidence Knowledge Graph"
        description="Interactive NetworkX + React Flow topology linking source documents, extracted claims, resolved entities, and conflicts."
      />

      {!activeAnalysisId ? (
        <NoAnalysisEmptyState />
      ) : (
        <>
          {error && (
            <Alert variant="destructive">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <div className="text-xs">{error}</div>
            </Alert>
          )}

          {/* Toolbar & Stats */}
          <Card>
            <CardContent className="flex flex-wrap items-center justify-between gap-4 p-4">
              <div className="flex flex-wrap items-center gap-2">
                <div className="relative">
                  <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
                  <input
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Filter entity, claim, file..."
                    className="h-9 w-56 rounded-lg border border-slate-700 bg-[#071026] pl-9 pr-3 text-xs text-slate-100 outline-none focus:border-cyan-500"
                  />
                </div>

                {(
                  [
                    ["document", "Documents"],
                    ["claim", "Claims"],
                    ["entity", "Entities"],
                    ["conflict", "Conflicts"],
                  ] as const
                ).map(([key, label]) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() =>
                      setVisibleTypes((prev) => ({ ...prev, [key]: !prev[key] }))
                    }
                    className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition ${
                      visibleTypes[key]
                        ? "border-cyan-500/40 bg-cyan-500/15 text-cyan-200"
                        : "border-slate-800 bg-[#071026] text-slate-500"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>

              {graphData && (
                <div className="flex flex-wrap items-center gap-2 text-xs text-slate-300">
                  <Badge variant="info">{graphData.statistics.documents} Docs</Badge>
                  <Badge variant="purple">{graphData.statistics.claims} Claims</Badge>
                  <Badge variant="default">{graphData.statistics.entities} Entities</Badge>
                  <Badge variant="danger">{graphData.statistics.conflicts} Conflicts</Badge>
                </div>
              )}
            </CardContent>
          </Card>

          <div className="grid gap-4 lg:grid-cols-12">
            <Card className={selectedItem ? "lg:col-span-8" : "lg:col-span-12"}>
              <div className="h-[620px] w-full overflow-hidden rounded-xl bg-[#050b1a]">
                {loading ? (
                  <div className="flex h-full items-center justify-center text-sm text-slate-400">
                    <Network className="mr-2 h-4 w-4 animate-pulse text-cyan-400" />
                    Loading evidence graph...
                  </div>
                ) : (
                  <ReactFlow
                    nodes={nodes}
                    edges={edges}
                    nodeTypes={NODE_TYPES}
                    onNodesChange={onNodesChange}
                    onEdgesChange={onEdgesChange}
                    onNodeClick={(_e, node) =>
                      setSelectedItem({
                        kind: "node",
                        title: String(node.data.label ?? node.id),
                        data: { id: node.id, type: node.type, ...node.data },
                      })
                    }
                    onEdgeClick={(_e, edge) =>
                      setSelectedItem({
                        kind: "edge",
                        title: String(edge.label ?? "Relationship"),
                        data: {
                          source: edge.source,
                          target: edge.target,
                          ...(edge.data ?? {}),
                        },
                      })
                    }
                    fitView
                    minZoom={0.2}
                    maxZoom={1.8}
                  >
                    <Background color="#1e293b" gap={20} />
                    <Controls />
                    <MiniMap
                      nodeColor={(n) =>
                        n.type === "conflict"
                          ? "#f43f5e"
                          : n.type === "document"
                          ? "#3b82f6"
                          : n.type === "entity"
                          ? "#22d3ee"
                          : "#a855f7"
                      }
                      maskColor="rgba(6, 13, 31, 0.75)"
                    />
                  </ReactFlow>
                )}
              </div>
            </Card>

            {selectedItem && (
              <Card className="lg:col-span-4">
                <CardHeader className="flex flex-row items-center justify-between space-y-0 border-b border-slate-800 pb-3">
                  <div className="flex items-center gap-2">
                    <GitBranch className="h-4 w-4 text-cyan-400" />
                    <CardTitle className="truncate">{selectedItem.title}</CardTitle>
                  </div>
                  <button
                    type="button"
                    onClick={() => setSelectedItem(null)}
                    className="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-white"
                    aria-label="Close inspector"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </CardHeader>
                <CardContent className="max-h-[550px] space-y-2.5 overflow-y-auto pt-4 text-xs">
                  <Badge variant="default">{selectedItem.kind.toUpperCase()}</Badge>
                  {Object.entries(selectedItem.data).map(([k, v]) => {
                    if (v === null || v === undefined || v === "") return null;
                    return (
                      <div
                        key={k}
                        className="rounded-lg border border-slate-800 bg-[#071026] px-3 py-2"
                      >
                        <div className="text-[10px] uppercase tracking-wider text-slate-500">
                          {k.replace(/_/g, " ")}
                        </div>
                        <div className="mt-0.5 break-words font-mono text-slate-200">
                          {Array.isArray(v) ? v.join(", ") || "—" : String(v)}
                        </div>
                      </div>
                    );
                  })}
                </CardContent>
              </Card>
            )}
          </div>
        </>
      )}
    </div>
  );
}

export default EvidenceGraphPage;
