const path = require('path')

const MIGRATIONS_DIR = path.resolve(__dirname, 'src/migrations')

module.exports = (options) => {
  return {
    ...options,
    // Migrations are NOT bundled: TypeORM require()s each file at runtime through a
    // glob (dist/migrations/*.js), so every migration must stay a standalone module.
    // They are compiled separately by `tsc -p tsconfig.migrations.json` (see `build`).
    module: {
      ...options.module,
      rules: (options.module?.rules ?? []).map((rule) => {
        if (!rule || typeof rule !== 'object' || !rule.test) return rule
        const existing = rule.exclude
        const excludes = Array.isArray(existing) ? existing : existing ? [existing] : []
        return { ...rule, exclude: [...excludes, MIGRATIONS_DIR] }
      }),
    },
    externals: [
      // Bundle @ai-voice/shared by not marking it as external
      (ctx, callback) => {
        const req = typeof ctx === 'string' ? ctx : ctx.request
        if (req === '@ai-voice/shared' || (req && req.startsWith('@ai-voice/shared/'))) {
          return callback()
        }
        // Delegate everything else to the original externals
        const originals = Array.isArray(options.externals)
          ? options.externals
          : options.externals
          ? [options.externals]
          : []
        if (originals.length === 0) return callback()
        let i = 0
        const tryNext = () => {
          if (i >= originals.length) return callback()
          const ext = originals[i++]
          if (typeof ext === 'function') ext(ctx, callback)
          else tryNext()
        }
        tryNext()
      },
    ],
  }
}
