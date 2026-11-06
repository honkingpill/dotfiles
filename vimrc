call plug#begin()
Plug 'tpope/vim-commentary'
Plug 'tpope/vim-surround'
Plug 'godlygeek/tabular'
Plug 'vim-airline/vim-airline'
Plug 'scrooloose/nerdtree'
call plug#end()
"  vim-commentary {{{  
"  Добавлять типы если не работает по алгоритму: 
"  1. :set ft? (x) 
"  2  autocmd FileType x setlocal commentstring=\#\ %s 
autocmd FileType vim setlocal commentstring=\"\ %s
" }}} 
set nocompatible 
syntax on
set number
set relativenumber
set tabstop=3
set softtabstop=3
set shiftwidth=3
set ignorecase smartcase
set wrap
set colorcolumn=4,40
set scrolloff=8
set cursorline
set expandtab
set foldmethod=marker
set foldlevelstart=0
set listchars=tab:→\ ,space:·,trail:•

set hlsearch
set incsearch
nnoremap <silent> <Esc> :nohls<CR>
nnoremap <silent> <Slash> :hls<CR>

function! ToggleTabs()
  if &expandtab
    set noexpandtab
    retab!
  else
    set expandtab
    retab
  endif
endfunction
nnoremap <leader>w :w<CR>
nnoremap <leader>q :q<CR>
nnoremap <leader>wq :wq<CR>
nnoremap <leader>r :source %<CR>
nnoremap <leader>ll :set list!<CR>
nnoremap <leader>lc :set cc=<CR>
nnoremap <leader>e :NERDTreeToggle<CR>
nnoremap <leader>t :call ToggleTabs()<CR>
