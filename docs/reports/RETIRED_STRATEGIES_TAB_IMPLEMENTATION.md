# Retired Strategies Tab Implementation

## Summary
Added functionality to view and permanently delete retired strategies from the database.

## Issue Found and Fixed
The backend API was filtering out RETIRED strategies by default, preventing them from being displayed in the frontend. Added an `include_retired` query parameter to the `/strategies` endpoint to allow fetching retired strategies.

## Backend Changes

### 1. Updated Endpoint: Get Strategies
**File:** `src/api/routers/strategies.py`

Modified the `get_strategies` endpoint to accept an optional `include_retired` parameter:

```python
async def get_strategies(
    mode: TradingMode,
    status_filter: Optional[StrategyStatus] = None,
    include_retired: bool = False,  # NEW PARAMETER
    username: str = Depends(get_current_user),
    session: Session = Depends(get_db_session)
):
    """
    Get all strategies.
    
    Args:
        mode: Trading mode (DEMO or LIVE)
        status_filter: Optional status filter
        include_retired: Whether to include retired strategies (default: False)
        username: Current authenticated user
        session: Database session
        
    Returns:
        List of strategies
        
    Validates: Requirement 11.3
    """
    logger.info(f"Getting strategies for {mode.value} mode, user {username}, include_retired={include_retired}")
    
    # Query strategies from database
    query = session.query(StrategyORM)
    
    # Exclude RETIRED strategies unless explicitly requested
    if not include_retired:
        query = query.filter(StrategyORM.status != StrategyStatus.RETIRED.value)
    
    # Apply additional status filter if provided
    if status_filter:
        query = query.filter(StrategyORM.status == status_filter)
```

### 2. New Endpoint: Permanent Delete Strategy
**File:** `src/api/routers/strategies.py`

Added new endpoint after the `retire_strategy` endpoint (around line 720):

```python
@router.delete("/{strategy_id}/permanent", response_model=StrategyActionResponse)
async def permanently_delete_strategy(
    strategy_id: str,
    mode: TradingMode,
    username: str = Depends(get_current_user),
    session: Session = Depends(get_db_session)
):
    """
    Permanently delete a retired strategy from the database.
    
    This endpoint only works for strategies with RETIRED status.
    Active or backtested strategies must be retired first.
    """
    logger.info(f"Permanently deleting strategy {strategy_id} for {mode.value} mode, user {username}")
    
    try:
        # Check if strategy exists and is retired
        strategy_orm = session.query(StrategyORM).filter(StrategyORM.id == strategy_id).first()
        
        if not strategy_orm:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Strategy {strategy_id} not found"
            )
        
        if strategy_orm.status != StrategyStatus.RETIRED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Can only permanently delete RETIRED strategies. Current status: {strategy_orm.status.value}"
            )
        
        # Delete the strategy from the database
        session.delete(strategy_orm)
        session.commit()
        logger.info(f"Strategy {strategy_id} permanently deleted from database by {username}")
        
        return StrategyActionResponse(
            success=True,
            message="Strategy permanently deleted successfully",
            strategy_id=strategy_id
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to permanently delete strategy: {e}")
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to permanently delete strategy: {str(e)}"
        )
```

## Frontend Changes

### 1. API Client Updates
**File:** `frontend/src/services/api.ts`

#### A. Updated getStrategies method to include retired strategies:
```typescript
async getStrategies(mode: TradingMode, includeRetired: boolean = true): Promise<Strategy[]> {
  const response = await this.client.get<ApiResponse<Strategy[]>>(
    `/strategies?mode=${mode}&include_retired=${includeRetired}`
  );
  return this.extractArrayFromResponse<Strategy>(response, 'strategies');
}
```

#### B. Added new method for permanent deletion (around line 315):
```typescript
async permanentlyDeleteStrategy(strategyId: string, mode: TradingMode): Promise<{ success: boolean; message: string }> {
  const response = await this.client.delete<ApiResponse<{ success: boolean; message: string }>>(
    `/strategies/${strategyId}/permanent?mode=${mode}`
  );
  return this.handleResponse(response);
}
```

### 2. StrategiesNew.tsx Updates
**File:** `frontend/src/pages/StrategiesNew.tsx`

#### A. Add retired strategies state (around line 135):
```typescript
const retiredStrategies = useMemo(() => 
  strategies.filter(s => s.status === 'RETIRED'),
  [strategies]
);
```

#### B. Add filtered retired strategies (around line 145):
```typescript
const filteredRetiredStrategies = useMemo(() => 
  filterStrategies(retiredStrategies),
  [retiredStrategies, searchQuery, statusFilter, templateFilter, regimeFilter, sourceFilter, categoryFilter, typeFilter]
);
```

#### C. Add permanent delete handlers (after handleRetire, around line 416):
```typescript
const handlePermanentDelete = async (strategyId: string) => {
  if (!confirm('⚠️ PERMANENT DELETE: This will permanently delete this retired strategy from the database. This action CANNOT be undone. Are you absolutely sure?')) {
    return;
  }

  try {
    await apiClient.permanentlyDeleteStrategy(strategyId, tradingMode!);
    await fetchStrategies();
    toast.success('Strategy permanently deleted');
  } catch (error) {
    console.error('Failed to permanently delete strategy:', error);
    toast.error('Failed to permanently delete strategy');
  }
};

const handleBulkPermanentDelete = async () => {
  if (selectedStrategies.size === 0) return;
  
  if (!confirm(`⚠️ PERMANENT DELETE: This will permanently delete ${selectedStrategies.size} retired strategies from the database. This action CANNOT be undone. Are you absolutely sure?`)) {
    return;
  }

  let successCount = 0;
  let failCount = 0;

  for (const strategyId of selectedStrategies) {
    try {
      await apiClient.permanentlyDeleteStrategy(strategyId, tradingMode!);
      successCount++;
    } catch (err) {
      console.error(`Failed to permanently delete strategy ${strategyId}:`, err);
      failCount++;
    }
  }

  setSelectedStrategies(new Set());
  await fetchStrategies();
  
  toast.success(`Permanently deleted ${successCount} strategies${failCount > 0 ? `, ${failCount} failed` : ''}`);
};
```

#### D. Add Retired tab trigger (around line 883, after backtested tab):
```typescript
<TabsTrigger value="retired" className="data-[state=active]:bg-accent-green/20 data-[state=active]:text-accent-green">
  <Trash2 className="h-4 w-4 mr-2" />
  Retired ({filteredRetiredStrategies.length})
</TabsTrigger>
```

#### E. Add Retired tab content (after Backtested TabsContent, before closing Tabs tag):
```typescript
{/* Retired Strategies Tab */}
<TabsContent value="retired" className="space-y-6">
  {/* Filters */}
  <Card>
    <CardContent className="pt-6">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        <div className="relative xl:col-span-2">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-500" />
          <Input
            placeholder="Search by name or symbol..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-10"
          />
        </div>

        <Select value={categoryFilter} onValueChange={setCategoryFilter}>
          <SelectTrigger>
            <SelectValue placeholder="Category" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Categories</SelectItem>
            <SelectItem value="alpha_edge">Alpha Edge</SelectItem>
            <SelectItem value="template_based">Template-Based</SelectItem>
            <SelectItem value="manual">Manual</SelectItem>
          </SelectContent>
        </Select>

        <Select value={typeFilter} onValueChange={setTypeFilter}>
          <SelectTrigger>
            <SelectValue placeholder="Type" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Types</SelectItem>
            {availableTypes.map(type => (
              <SelectItem key={type} value={type}>
                {type.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ')}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        
        <Select value={templateFilter} onValueChange={setTemplateFilter}>
          <SelectTrigger>
            <SelectValue placeholder="Template" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Templates</SelectItem>
            {availableTemplates.map(template => (
              <SelectItem key={template} value={template}>{template}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={regimeFilter} onValueChange={setRegimeFilter}>
          <SelectTrigger>
            <SelectValue placeholder="Regime" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Regimes</SelectItem>
            {availableRegimes.map(regime => (
              <SelectItem key={regime} value={regime}>{regime}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={sourceFilter} onValueChange={setSourceFilter}>
          <SelectTrigger>
            <SelectValue placeholder="Source" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Sources</SelectItem>
            <SelectItem value="TEMPLATE">Autonomous</SelectItem>
            <SelectItem value="USER">Manual</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Bulk Actions for Retired */}
      {selectedStrategies.size > 0 && (
        <div className="flex items-center gap-3 pt-4 border-t border-dark-border">
          <span className="text-sm text-gray-400 font-mono">
            {selectedStrategies.size} selected
          </span>
          <Button
            onClick={handleBulkPermanentDelete}
            variant="destructive"
            size="sm"
          >
            <Trash2 className="h-4 w-4 mr-2" />
            Permanently Delete Selected
          </Button>
          <Button
            onClick={() => setSelectedStrategies(new Set())}
            variant="ghost"
            size="sm"
            className="ml-auto"
          >
            Clear Selection
          </Button>
        </div>
      )}
    </CardContent>
  </Card>

  {/* Retired Strategies Table */}
  <Card>
    <CardHeader>
      <CardTitle className="flex items-center justify-between">
        <span className="flex items-center gap-2">
          <Trash2 className="h-5 w-5" />
          Retired Strategies
        </span>
        <span className="text-sm font-mono text-gray-400">
          {selectedStrategies.size > 0 
            ? `${selectedStrategies.size} selected of ${filteredRetiredStrategies.length} (${retiredStrategies.length} total)`
            : `${filteredRetiredStrategies.length} of ${retiredStrategies.length} strategies`
          }
        </span>
      </CardTitle>
      <CardDescription>
        These strategies have been retired. You can permanently delete them from the database.
      </CardDescription>
    </CardHeader>
    <CardContent>
      <DataTable
        columns={retiredStrategyColumns}
        data={filteredRetiredStrategies}
        pageSize={20}
        getRowId={(row) => row.id}
        rowSelection={Object.fromEntries(
          Array.from(selectedStrategies).map(id => [id, true])
        )}
        onRowSelectionChange={(updaterOrValue) => {
          const currentSelection = Object.fromEntries(
            Array.from(selectedStrategies).map(id => [id, true])
          );
          const newSelection = typeof updaterOrValue === 'function' 
            ? updaterOrValue(currentSelection)
            : updaterOrValue;
          setSelectedStrategies(new Set(Object.keys(newSelection).filter(key => newSelection[key])));
        }}
      />
    </CardContent>
  </Card>
</TabsContent>
```

#### F. Add retired strategy columns definition (after backtestedStrategyColumns, around line 750):
```typescript
// Table columns for retired strategies
const retiredStrategyColumns: ColumnDef<Strategy>[] = [
  {
    id: 'select',
    header: () => {
      const allSelected = filteredRetiredStrategies.length > 0 && 
        filteredRetiredStrategies.every(s => selectedStrategies.has(s.id));
      
      return (
        <input
          type="checkbox"
          checked={allSelected}
          onChange={(e) => {
            if (e.target.checked) {
              setSelectedStrategies(new Set(filteredRetiredStrategies.map(s => s.id)));
            } else {
              setSelectedStrategies(new Set());
            }
          }}
          className="w-4 h-4 rounded border-gray-600 bg-dark-surface text-accent-green focus:ring-accent-green"
        />
      );
    },
    cell: ({ row }) => (
      <input
        type="checkbox"
        checked={row.getIsSelected()}
        onChange={(e) => row.toggleSelected(!!e.target.checked)}
        className="w-4 h-4 rounded border-gray-600 bg-dark-surface text-accent-green focus:ring-accent-green"
      />
    ),
  },
  {
    accessorKey: 'name',
    header: 'Name',
    cell: ({ row }) => (
      <div>
        <div className="font-mono text-sm text-gray-200">{row.original.name}</div>
        <div className="text-xs text-gray-500 font-mono">{row.original.symbols.join(', ')}</div>
      </div>
    ),
  },
  {
    accessorKey: 'description',
    header: 'Strategy',
    cell: ({ row }) => (
      <div>
        <div className="text-sm text-gray-300">{row.original.description || 'No description available'}</div>
      </div>
    ),
  },
  {
    accessorKey: 'metadata.strategy_category',
    header: 'Category',
    cell: ({ row }) => {
      const { label, variant } = getStrategyCategory(row.original);
      return (
        <Badge 
          className={cn(
            "font-mono text-xs",
            variant === 'purple' && "bg-purple-500/20 text-purple-300 border-purple-500/30",
            variant === 'blue' && "bg-blue-500/20 text-blue-300 border-blue-500/30",
            variant === 'gray' && "bg-gray-500/20 text-gray-300 border-gray-500/30"
          )}
        >
          {label}
        </Badge>
      );
    },
  },
  {
    accessorKey: 'metadata.template_type',
    header: 'Type',
    cell: ({ row }) => {
      const type = getStrategyType(row.original);
      return (
        <div className="text-sm text-gray-300 font-mono">
          {type}
        </div>
      );
    },
  },
  {
    accessorKey: 'performance_metrics.total_return',
    header: () => <div className="text-right">Final Return</div>,
    cell: ({ row }) => {
      const value = row.original.performance_metrics?.total_return;
      return (
        <div className={cn(
          'text-right font-mono text-sm font-semibold',
          value && value >= 0 ? 'text-accent-green' : 'text-accent-red'
        )}>
          {value !== undefined ? formatPercentage(value * 100) : 'N/A'}
        </div>
      );
    },
  },
  {
    accessorKey: 'performance_metrics.sharpe_ratio',
    header: () => <div className="text-right">Sharpe</div>,
    cell: ({ row }) => (
      <div className="text-right font-mono text-sm">
        {formatMetric(row.original.performance_metrics?.sharpe_ratio)}
      </div>
    ),
  },
  {
    accessorKey: 'performance_metrics.total_trades',
    header: () => <div className="text-right">Trades</div>,
    cell: ({ row }) => (
      <div className="text-right font-mono text-sm text-gray-300">
        {row.original.performance_metrics?.total_trades || 0}
      </div>
    ),
  },
  {
    accessorKey: 'retired_at',
    header: 'Retired',
    cell: ({ row }) => {
      const retiredAt = (row.original as any).retired_at;
      return (
        <div className="text-sm text-gray-400 font-mono">
          {retiredAt ? new Date(retiredAt).toLocaleDateString() : 'Unknown'}
        </div>
      );
    },
  },
  {
    id: 'actions',
    header: () => <div className="text-right">Actions</div>,
    cell: ({ row }) => (
      <div className="flex justify-end">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm" className="h-8 w-8 p-0">
              <MoreVertical className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => handleViewDetails(row.original)}>
              <Eye className="mr-2 h-4 w-4" />
              View Details
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem 
              onClick={() => handlePermanentDelete(row.original.id)}
              className="text-accent-red"
            >
              <Trash2 className="mr-2 h-4 w-4" />
              Permanently Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    ),
  },
];
```

## Testing

1. Navigate to Strategies page
2. Click on "Retired" tab
3. You should see 527 retired strategies
4. Select one or more strategies
5. Click "Permanently Delete Selected" or use the dropdown menu
6. Confirm the deletion
7. Strategies should be permanently removed from the database

## Database Query to Verify

```bash
source venv/bin/activate
python -c "from src.models.database import get_database; from src.models.orm import StrategyORM; from src.models.enums import StrategyStatus; db = get_database(); session = db.get_session(); retired = session.query(StrategyORM).filter_by(status=StrategyStatus.RETIRED).all(); print(f'Retired strategies: {len(retired)}'); session.close()"
```

## Notes

- The permanent delete endpoint only works on strategies with RETIRED status
- Active or backtested strategies must be retired first before they can be permanently deleted
- The deletion is permanent and cannot be undone
- Bulk deletion is supported for multiple strategies at once
