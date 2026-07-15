import type { ReactElement } from 'react';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppProviders } from '../app/AppProviders';

export function renderWithProviders(element: ReactElement, route = '/') {
  return render(
    <MemoryRouter
      initialEntries={[route]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AppProviders>{element}</AppProviders>
    </MemoryRouter>,
  );
}
