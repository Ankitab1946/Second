namespace ExcelFinanceAddIn
{
    partial class RibbonFinance : Microsoft.Office.Tools.Ribbon.RibbonBase
    {
        private System.ComponentModel.IContainer components = null;

        public RibbonFinance()
            : base(Globals.Factory.GetRibbonFactory())
        {
            InitializeComponent();
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing && (components != null)) components.Dispose();
            base.Dispose(disposing);
        }

        #region Component Designer generated code

        private void InitializeComponent()
        {
            this.tabFinance = this.Factory.CreateRibbonTab();
            this.groupAPI = this.Factory.CreateRibbonGroup();

            this.btnFetchCounterparties = this.Factory.CreateRibbonButton();
            this.drpCounterparties = this.Factory.CreateRibbonDropDown();
            this.btnSubmitCounterparty = this.Factory.CreateRibbonButton();

            this.drpCurrency = this.Factory.CreateRibbonDropDown();
            this.drpPeriod = this.Factory.CreateRibbonDropDown();
            this.drpBasis = this.Factory.CreateRibbonDropDown();
            this.drpType = this.Factory.CreateRibbonDropDown();

            this.numFromYear = this.Factory.CreateRibbonEditBox();
            this.numToYear = this.Factory.CreateRibbonEditBox();

            this.btnShowBalanceSheet = this.Factory.CreateRibbonButton();

            // 
            // tabFinance
            // 
            this.tabFinance.Label = "Finance Tools";
            this.tabFinance.Name = "tabFinance";
            this.tabFinance.Groups.Add(this.groupAPI);

            // 
            // groupAPI
            // 
            this.groupAPI.Label = "API Workflow";
            this.groupAPI.Name = "groupAPI";

            this.groupAPI.Items.Add(this.btnFetchCounterparties);
            this.groupAPI.Items.Add(this.drpCounterparties);
            this.groupAPI.Items.Add(this.btnSubmitCounterparty);

            this.groupAPI.Items.Add(this.drpCurrency);
            this.groupAPI.Items.Add(this.drpPeriod);
            this.groupAPI.Items.Add(this.drpBasis);
            this.groupAPI.Items.Add(this.drpType);

            this.groupAPI.Items.Add(this.numFromYear);
            this.groupAPI.Items.Add(this.numToYear);

            this.groupAPI.Items.Add(this.btnShowBalanceSheet);

            // 
            // btnFetchCounterparties
            // 
            this.btnFetchCounterparties.Label = "Fetch from API";
            this.btnFetchCounterparties.Name = "btnFetchCounterparties";
            this.btnFetchCounterparties.ScreenTip = "Fetch Counterparties";
            this.btnFetchCounterparties.SuperTip = "Retrieve Counterparty List from API";
            this.btnFetchCounterparties.Click += new Microsoft.Office.Tools.Ribbon.RibbonControlEventHandler(this.btnFetchCounterparties_Click);

            // 
            // drpCounterparties
            // 
            this.drpCounterparties.Label = "Counterparty";
            this.drpCounterparties.Name = "drpCounterparties";

            // 
            // btnSubmitCounterparty
            // 
            this.btnSubmitCounterparty.Label = "Submit Counterparty";
            this.btnSubmitCounterparty.Name = "btnSubmitCounterparty";
            this.btnSubmitCounterparty.ScreenTip = "Submit Counterparty Selection";
            this.btnSubmitCounterparty.SuperTip = "Submit and fetch Counterparty details";
            this.btnSubmitCounterparty.Click += new Microsoft.Office.Tools.Ribbon.RibbonControlEventHandler(this.btnSubmitCounterparty_Click);

            // 
            // drpCurrency
            // 
            this.drpCurrency.Label = "Currency";
            this.drpCurrency.Name = "drpCurrency";

            // 
            // drpPeriod
            // 
            this.drpPeriod.Label = "Period";
            this.drpPeriod.Name = "drpPeriod";

            // 
            // drpBasis
            // 
            this.drpBasis.Label = "Basis";
            this.drpBasis.Name = "drpBasis";

            // 
            // drpType
            // 
            this.drpType.Label = "Type";
            this.drpType.Name = "drpType";

            // 
            // numFromYear
            // 
            this.numFromYear.Label = "From Year";
            this.numFromYear.Name = "numFromYear";
            this.numFromYear.Text = "2007";

            // 
            // numToYear
            // 
            this.numToYear.Label = "To Year";
            this.numToYear.Name = "numToYear";
            this.numToYear.Text = "2008";

            // 
            // btnShowBalanceSheet
            // 
            this.btnShowBalanceSheet.Label = "Fetch Final Data";
            this.btnShowBalanceSheet.Name = "btnShowBalanceSheet";
            this.btnShowBalanceSheet.ScreenTip = "Fetch Final Data";
            this.btnShowBalanceSheet.SuperTip = "Retrieve Balance Sheet based on selected parameters";
            this.btnShowBalanceSheet.Click += new Microsoft.Office.Tools.Ribbon.RibbonControlEventHandler(this.btnShowBalanceSheet_Click);

            // 
            // RibbonFinance
            // 
            this.Name = "RibbonFinance";
            this.RibbonType = "Microsoft.Excel.Workbook";
            this.Tabs.Add(this.tabFinance);
            this.Load += new Microsoft.Office.Tools.Ribbon.RibbonUIEventHandler(this.RibbonFinance_Load);
        }

        #endregion

        internal Microsoft.Office.Tools.Ribbon.RibbonTab tabFinance;
        internal Microsoft.Office.Tools.Ribbon.RibbonGroup groupAPI;

        internal Microsoft.Office.Tools.Ribbon.RibbonButton btnFetchCounterparties;
        internal Microsoft.Office.Tools.Ribbon.RibbonDropDown drpCounterparties;
        internal Microsoft.Office.Tools.Ribbon.RibbonButton btnSubmitCounterparty;

        internal Microsoft.Office.Tools.Ribbon.RibbonDropDown drpCurrency;
        internal Microsoft.Office.Tools.Ribbon.RibbonDropDown drpPeriod;
        internal Microsoft.Office.Tools.Ribbon.RibbonDropDown drpBasis;
        internal Microsoft.Office.Tools.Ribbon.RibbonDropDown drpType;

        internal Microsoft.Office.Tools.Ribbon.RibbonEditBox numFromYear;
        internal Microsoft.Office.Tools.Ribbon.RibbonEditBox numToYear;

        internal Microsoft.Office.Tools.Ribbon.RibbonButton btnShowBalanceSheet;
    }

    partial class ThisRibbonCollection
    {
        internal RibbonFinance RibbonFinance
        {
            get { return this.GetRibbon<RibbonFinance>(); }
        }
    }
}
