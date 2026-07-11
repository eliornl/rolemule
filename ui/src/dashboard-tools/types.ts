export type AlertType = 'success' | 'danger' | 'warning' | 'info';

export interface ToolErrorResponse {
  message?: string;
  detail?: string;
}

export interface JobComparisonJobInput {
  title: string;
  company: string;
  description: string | null;
}

export interface DecisionFactor {
  factor?: string;
  winner?: string;
  importance?: string;
  explanation?: string;
}

export interface PushbackResponse {
  scenario?: string;
  response_script?: string;
}

export interface AlternativeAsk {
  item?: string;
  value?: string;
  likelihood?: string;
}

export interface SalaryScriptSection {
  label: string;
  key: string;
  icon: string;
}
