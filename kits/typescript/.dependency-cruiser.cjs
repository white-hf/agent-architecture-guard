// dependency-cruiser rules (npx depcruise src --config .dependency-cruiser.cjs).
// Layout: src/<domain>/{web,application,domain,persistence}/...
/** @type {import('dependency-cruiser').IConfiguration} */
module.exports = {
  forbidden: [
    { name: "domain-is-pure", severity: "error",
      from: { path: "^src/[^/]+/domain/" },
      to: { path: "^src/[^/]+/(application|persistence|web)/|node_modules/(pg|mysql2|typeorm|prisma|@prisma|express|fastify)" } },
    { name: "web-not-to-persistence", severity: "error",
      from: { path: "^src/[^/]+/web/" }, to: { path: "^src/[^/]+/persistence/" } },
    { name: "no-other-domains-persistence", severity: "error",
      comment: "use the owning domain's application service",
      from: { path: "^src/([^/]+)/" }, to: { path: "^src/([^/]+)/persistence/", pathNot: "^src/$1/persistence/" } },
    { name: "no-cycles", severity: "error", from: {}, to: { circular: true } },
  ],
  options: { tsConfig: { fileName: "tsconfig.json" }, doNotFollow: { path: "node_modules" } },
};
