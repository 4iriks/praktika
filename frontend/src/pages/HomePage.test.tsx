import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes, useLocation } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { HomePage } from './HomePage';
import { renderWithProviders } from '../test/render';

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{location.pathname + location.search}</output>;
}

describe('HomePage', () => {
  it('отображает поисковую форму', () => {
    renderWithProviders(<HomePage />);
    expect(screen.getByRole('search')).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Поисковый запрос' })).toBeInTheDocument();
    expect(
      screen.getByText('Поиск и ответы по русскоязычной базе знаний Python'),
    ).toBeInTheDocument();
  });

  it('создаёт URL со всеми основными параметрами', async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/search" element={<LocationProbe />} />
      </Routes>,
    );

    await user.type(screen.getByRole('textbox', { name: 'Поисковый запрос' }), 'asyncio');
    await user.click(screen.getByRole('button', { name: 'Получить ответ ИИ' }));
    await user.click(screen.getByRole('button', { name: /Запустить/ }));

    expect(await screen.findByTestId('location')).toHaveTextContent(
      '/search?q=asyncio&view=answer&mode=hybrid&page=1&sort=relevance',
    );
  });
});
