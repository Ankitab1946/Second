using System;
using System.Collections.Generic;
using System.Data;
using System.Net.Http;
using System.Threading.Tasks;
using System.Windows.Forms;
using Microsoft.Office.Tools.Ribbon;
using Newtonsoft.Json;

namespace ExcelFinanceAddIn
{
    public partial class RibbonFinance
    {
        // Store API1 response
        public List<Counterparty> CounterpartyList { get; set; } = new List<Counterparty>();

        private async void btnFetchAPI_Click(object sender, RibbonControlEventArgs e)
        {
            try
            {
                using (var client = new HttpClient())
                {
                    client.BaseAddress = new Uri("https://api.yourcompany.com/");
                    var resp = await client.GetAsync("counterparties");
                    resp.EnsureSuccessStatusCode();
                    string json = await resp.Content.ReadAsStringAsync();

                    var cpList = JsonConvert.DeserializeObject<List<Counterparty>>(json);
                    var top5 = cpList.Count > 5 ? cpList.GetRange(0, 5) : cpList;

                    ddlCounterparty.Items.Clear();
                    foreach (var cp in top5)
                        ddlCounterparty.Items.Add(cp.CID);

                    CounterpartyList = top5;
                }
            }
            catch (Exception ex)
            {
                MessageBox.Show("Error fetching Counterparties: " + ex.Message);
            }
        }

        private void ddlCounterparty_SelectionChanged(object sender, RibbonControlEventArgs e)
        {
            try
            {
                var selectedCID = ddlCounterparty.SelectedItem.Label;
                var cp = CounterpartyList.Find(c => c.CID == selectedCID);

                if (cp != null)
                {
                    string msg = $"CID\tCName\tShortName\n{cp.CID}\t{cp.CName}\t{cp.ShortName}";
                    MessageBox.Show(msg, "Counterparty Details");
                }
            }
            catch (Exception ex)
            {
                MessageBox.Show("Error showing Counterparty: " + ex.Message);
            }
        }

        private async void btnSubmitCounterparty_Click(object sender, RibbonControlEventArgs e)
        {
            try
            {
                var selectedCID = ddlCounterparty.SelectedItem.Label;
                var payload = new { CID = selectedCID };

                using (var client = new HttpClient())
                {
                    client.BaseAddress = new Uri("https://api.yourcompany.com/");
                    var content = new StringContent(JsonConvert.SerializeObject(payload),
                                                    System.Text.Encoding.UTF8, "application/json");
                    var resp = await client.PostAsync("api2", content);
                    resp.EnsureSuccessStatusCode();
                    string json = await resp.Content.ReadAsStringAsync();

                    dynamic api2Resp = JsonConvert.DeserializeObject(json);

                    // Populate dropdowns
                    ddlCurrency.Items.Clear();
                    ddlCurrency.Items.Add(api2Resp.Currency.ToString());
                    ddlCurrency.SelectedItemIndex = 0;

                    ddlPeriod.Items.Clear();
                    foreach (var p in api2Resp.Period)
                        ddlPeriod.Items.Add(p.ToString());
                    ddlPeriod.SelectedItemIndex = 0;

                    ddlBasis.Items.Clear();
                    foreach (var b in api2Resp.Basis)
                        ddlBasis.Items.Add(b.ToString());
                    ddlBasis.SelectedItemIndex = 1; // default text2

                    ddlType.Items.Clear();
                    foreach (var t in api2Resp.Type)
                        ddlType.Items.Add(t.ToString());
                    ddlType.SelectedItemIndex = 0;

                    txtFromYear.Text = api2Resp.FromYear.ToString();
                    txtToYear.Text = api2Resp.ToYear.ToString();
                }
            }
            catch (Exception ex)
            {
                MessageBox.Show("Error submitting Counterparty: " + ex.Message);
            }
        }

        private async void btnFetchFinalData_Click(object sender, RibbonControlEventArgs e)
        {
            try
            {
                var payload = new
                {
                    CID = ddlCounterparty.SelectedItem.Label,
                    FromYear = int.Parse(txtFromYear.Text),
                    toYear = int.Parse(txtToYear.Text),
                    Period = ddlPeriod.SelectedItem.Label,
                    Basis = ddlBasis.SelectedItem.Label,
                    Type = ddlType.SelectedItem.Label,
                };

                using (var client = new HttpClient())
                {
                    client.BaseAddress = new Uri("https://api.yourcompany.com/");
                    var content = new StringContent(JsonConvert.SerializeObject(payload),
                                                    System.Text.Encoding.UTF8, "application/json");

                    var resp = await client.PostAsync("api3", content);
                    resp.EnsureSuccessStatusCode();
                    string json = await resp.Content.ReadAsStringAsync();

                    DataTable dt = JsonConvert.DeserializeObject<DataTable>(json);
                    Utils.ExcelWriter.WriteToExcel(dt, "Final Data");
                }
            }
            catch (Exception ex)
            {
                MessageBox.Show("Error fetching final data: " + ex.Message);
            }
        }
    }

    public class Counterparty
    {
        public string CID { get; set; }
        public string CName { get; set; }
        public string ShortName { get; set; }
    }
}
