import type { GenerationCandidate, Stage } from '../../types'

interface Props {
  candidate: GenerationCandidate
  stage: Stage
  onSelect: () => void
  isSelected: boolean
}

export default function CandidateView({ candidate, stage, onSelect, isSelected }: Props) {
  const formattedJson =
    candidate.parsed_output_json != null
      ? JSON.stringify(candidate.parsed_output_json, null, 2)
      : null

  return (
    <div
      className={`p-3 rounded-lg border text-sm ${
        candidate.error_code
          ? 'border-red-300 bg-red-50'
          : isSelected
            ? 'border-green-300 bg-green-50'
            : 'border-gray-200 bg-white'
      }`}
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="px-2 py-0.5 text-xs font-medium bg-gray-100 text-gray-700 rounded-full">
            第 {candidate.attempt_number} 次
          </span>
          {candidate.provider_id && (
            <span className="text-xs text-gray-500">
              {candidate.provider_id}
              {candidate.model_id ? ` / ${candidate.model_id}` : ''}
            </span>
          )}
          {isSelected && (
            <span className="px-1.5 py-0.5 text-xs font-medium bg-green-200 text-green-800 rounded">
              已选择
            </span>
          )}
        </div>

        <div className="flex items-center gap-3 text-xs text-gray-400">
          {candidate.input_tokens != null && (
            <span>输入: {candidate.input_tokens.toLocaleString()} tokens</span>
          )}
          {candidate.output_tokens != null && (
            <span>输出: {candidate.output_tokens.toLocaleString()} tokens</span>
          )}
          {candidate.latency_ms != null && (
            <span>{(candidate.latency_ms / 1000).toFixed(1)}s</span>
          )}
        </div>
      </div>

      {candidate.error_code && (
        <div className="mb-2 p-2 rounded bg-red-100 text-red-700 text-xs">
          <span className="font-medium">错误: </span>
          {candidate.error_message || candidate.error_code}
          {candidate.raw_response && (
            <pre className="mt-1 text-xs whitespace-pre-wrap max-h-32 overflow-y-auto bg-red-50 p-1 rounded border border-red-200">
              {candidate.raw_response}
            </pre>
          )}
        </div>
      )}

      {!candidate.error_code && formattedJson && stage !== 'writer' && (
        <pre className="text-xs bg-gray-900 text-green-300 p-2 rounded max-h-64 overflow-auto whitespace-pre-wrap">
          {formattedJson}
        </pre>
      )}

      {!candidate.error_code && stage === 'writer' && candidate.text_output && (
        <pre className="text-xs bg-gray-50 p-2 rounded max-h-64 overflow-y-auto whitespace-pre-wrap border border-gray-200 text-gray-800 leading-relaxed">
          {candidate.text_output}
        </pre>
      )}

      {!candidate.error_code && !formattedJson && !candidate.text_output && (
        <p className="text-xs text-gray-400 italic">无输出内容</p>
      )}

      <div className="mt-2 flex items-center gap-2">
        {!isSelected && !candidate.error_code && (
          <button
            onClick={onSelect}
            className="px-3 py-1 text-xs font-medium bg-indigo-600 text-white rounded hover:bg-indigo-700 transition-colors"
          >
            选择此候选
          </button>
        )}
        {candidate.error_code && (
          <span className="text-xs text-red-500">此候选执行失败</span>
        )}
      </div>
    </div>
  )
}
