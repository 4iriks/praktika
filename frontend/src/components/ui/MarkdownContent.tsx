import ReactMarkdown from 'react-markdown';
import SyntaxHighlighter from 'react-syntax-highlighter/dist/esm/prism-light';
import python from 'react-syntax-highlighter/dist/esm/languages/prism/python';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import remarkGfm from 'remark-gfm';
import { cn } from '../../utils/cn';

SyntaxHighlighter.registerLanguage('python', python);

interface MarkdownContentProps {
  children: string;
  className?: string;
}

export function MarkdownContent({ children, className }: MarkdownContentProps) {
  return (
    <div className={cn('markdown-body', className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          code({ className: codeClassName, children: codeChildren }) {
            const language = /language-(\w+)/.exec(codeClassName ?? '')?.[1];
            const code =
              typeof codeChildren === 'string' || typeof codeChildren === 'number'
                ? String(codeChildren)
                : Array.isArray(codeChildren)
                  ? codeChildren
                      .filter(
                        (child): child is string | number =>
                          typeof child === 'string' || typeof child === 'number',
                      )
                      .join('')
                  : '';
            if (language) {
              return (
                <SyntaxHighlighter
                  language={language}
                  style={oneDark}
                  customStyle={{
                    margin: '1rem 0',
                    border: '1px solid rgb(var(--line))',
                    borderRadius: '0.65rem',
                    background: '#0b1020',
                    fontSize: '0.82rem',
                    lineHeight: '1.65',
                  }}
                  codeTagProps={{ style: { fontFamily: 'inherit' } }}
                  showLineNumbers
                >
                  {code.replace(/\n$/, '')}
                </SyntaxHighlighter>
              );
            }
            return <code className={codeClassName}>{codeChildren}</code>;
          },
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
