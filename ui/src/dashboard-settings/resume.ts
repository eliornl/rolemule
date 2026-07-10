import { getApiBase, getAuthToken } from '../shared/auth';
import { showAlert } from './notify';

export async function handleResumeUpload(input: HTMLInputElement): Promise<void> {
  const file = input.files?.[0];
  if (!file) return;

  const ext = `.${file.name.split('.').pop()?.toLowerCase() ?? ''}`;
  if (ext === '.doc') {
    showAlert(
      'Older Word (.doc) files are not supported. Save as .docx or PDF, then upload again.',
      'danger',
    );
    input.value = '';
    return;
  }
  if (!['.pdf', '.docx', '.txt'].includes(ext)) {
    showAlert('Please upload a PDF, Word (.docx), or TXT file.', 'danger');
    input.value = '';
    return;
  }

  const formData = new FormData();
  formData.append('resume', file);
  showAlert('Parsing your resume...', 'info', { loading: true });

  try {
    const response = await fetch(`${getApiBase()}/profile/parse-resume`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${getAuthToken()}` },
      body: formData,
    });
    if (response.ok) {
      const result = (await response.json()) as {
        success?: boolean;
        message?: string;
        data?: unknown;
      };
      if (result.success) {
        showAlert('Resume parsed! Redirecting to update your profile...', 'success');
        sessionStorage.setItem('parsedResumeData', JSON.stringify(result.data));
        window.setTimeout(() => {
          window.location.href = '/profile/setup?edit=true&fromResume=true';
        }, 1500);
      } else {
        throw new Error(result.message || 'Failed to parse resume');
      }
    } else {
      const errorData = (await response.json()) as { message?: string; detail?: string };
      throw new Error(errorData.message || errorData.detail || 'Failed to parse resume');
    }
  } catch (error) {
    const err = error as Error;
    console.error('Error uploading resume:', err);
    showAlert(err.message || 'Error parsing resume. Please try again.', 'danger');
  }
  input.value = '';
}
