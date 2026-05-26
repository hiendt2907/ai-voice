module.exports = (options) => {
  return {
    ...options,
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
