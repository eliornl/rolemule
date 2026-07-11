import { job3Visible, toolSubmitting } from './state';

export { setJob3Visible, setToolSubmitting } from './state';

export function getToolSubmitting(): boolean {
  return toolSubmitting;
}

export function getJob3Visible(): boolean {
  return job3Visible;
}
